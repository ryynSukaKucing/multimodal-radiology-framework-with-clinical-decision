import json
import os
import re
import time
from typing import List, Optional

import httpx
from PIL import Image
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

import ai_parsers
import models
from ai_parsers.segmentasi_anatomi.koreksi import midline_x
from llm_client import strip_low
from config import settings, resolve_authorization, router_key_managed, detect_max_tokens_for, segment_max_tokens_for, is_thinking_model
from database import get_db
from image_utils import save_uploaded_file, is_dicom_filename, DicomReadError, extract_dicom_meta, prepare_ai_image, content_bbox
from routers.history import _to_out, _structures_of
from security import get_current_user
router = APIRouter(prefix="/api", tags=["Pemindaian AI"])


# Jawaban meta dari model (bukan analisis citra), mis. "No radiological findings present; input contains a shell command".
_META_RX = re.compile(
    r"(shell command|not (?:a )?radiolog|input contains|cannot analy[sz]e|"
    r"no (?:image|picture) (?:was |is |has been )?(?:provided|attached|received|uploaded)|"
    r"unable to (?:view|see|analy[sz]e))", re.I)


def _is_invalid_result(res: dict, parse_mode: str) -> Optional[str]:
    """Alasan penolakan bila hasil bukan analisis citra yang sah, selain itu None."""
    if res.get("error"):
        return f"model menandai teks bukan analisis radiologi ({res['error']})"
    text = f"{res.get('diagnosis', '')} {res.get('summary', '')}"
    if _META_RX.search(text):
        return "diagnosis berisi teks meta, bukan temuan radiologi"
    if str(parse_mode).startswith("repair") and not res.get("anomalies") and not res.get("structures"):
        return "the repaired result has no findings or structures"
    if parse_mode == "text_fallback" and (res.get("summary") or "-").strip() in ("", "-"):
        return "the model returned no content"
    return None


def _reject_scan(db: Session, history_item, step, reason: str):
    """Catat sebagai error (BUKAN sukses) lalu hentikan dengan HTTP 502."""
    step(f"Result rejected: {reason}")
    history_item.status = "error"
    history_item.error_message = f"The model did not return a valid analysis: {reason}. Try again or choose another model."
    db.add(history_item)
    db.commit()
    raise HTTPException(status_code=502, detail=history_item.error_message)


@router.post("/dicom/preview")
async def dicom_preview(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
):
    """Mengunggah & membuka berkas (termasuk .dcm) untuk pratinjau cepat tanpa menjalankan AI."""
    file_bytes = await file.read()
    try:
        stored_filename, preview_filename, is_dicom, base64_jpeg = save_uploaded_file(
            file.filename, file_bytes
        )
    except DicomReadError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process the file: {e}")
    return {
        "is_dicom": is_dicom,
        "preview_url": f"/uploads/{preview_filename}",
        "base64_preview": f"data:image/jpeg;base64,{base64_jpeg}",
        "meta": extract_dicom_meta(file_bytes) if is_dicom else {},
    }


def _get_clinical_context(db: Session, patient_id: Optional[int]) -> str:
    if not patient_id:
        return ""
    ch = db.query(models.ClinicalHistory).filter(models.ClinicalHistory.patient_id == patient_id).first()
    if not ch:
        return ""
    parts = []
    labels = {
        "identitas_pasien": "Identitas Pasien",
        "keluhan_utama": "Keluhan Utama",
        "pemeriksaan_fisik": "Pemeriksaan Fisik",
        "pemeriksaan_penunjang": "Pemeriksaan Penunjang",
        "riwayat_medis": "Riwayat Medis",
        "keterangan_lainnya": "Keterangan Lainnya",
    }
    for field, label in labels.items():
        val = (getattr(ch, field, "") or "").strip()
        if val:
            parts.append(f"{label}: {val}")
    return "\n".join(parts)


def _post_payload_sync_note(resp_text: str) -> str:
    return (resp_text or "")[:300].replace("\n", " ")


async def _call_router(client: httpx.AsyncClient, payload: dict, headers: dict, steps) -> httpx.Response:
    """POST ke router AI. Jika router menolak `response_format` (HTTP 400), ulangi sekali tanpa field itu."""
    response = await client.post(settings.NINEROUTER_URL, json=payload, headers=headers)
    if response.status_code == 400 and "response_format" in payload and "response_format" in (response.text or "").lower():
        steps("Router menolak response_format, mengulang tanpa field tersebut")
        payload = {k: v for k, v in payload.items() if k != "response_format"}
        response = await client.post(settings.NINEROUTER_URL, json=payload, headers=headers)
    return response


def _message_from_response(response_data: dict):
    """Ambil (message_dict, finish_reason) dari respons chat-completions; toleran terhadap bentuk non-standar."""
    if not isinstance(response_data, dict):
        raise ValueError("The router response is not a JSON object.")
    choices = response_data.get("choices")
    if not choices:
        err = response_data.get("error")
        if err:
            raise ValueError(f"The router returned an error: {ai_parsers.extract_text(err)[:300]}")
        # sebagian router (gaya Anthropic/Responses) memakai 'content'/'output' di tingkat atas
        for k in ("content", "output", "output_text", "text"):
            if response_data.get(k):
                return {"content": response_data[k]}, None
        raise ValueError("Invalid model response (no 'choices').")
    ch = choices[0] or {}
    msg = ch.get("message")
    if msg is None and ch.get("text") is not None:    # gaya completions lama
        msg = {"content": ch.get("text")}
    return (msg or {}), ch.get("finish_reason")


async def _run_single_scan(
    db: Session,
    file: UploadFile,
    file_bytes: bytes,
    model_name: str,
    patient_id: Optional[int],
    authorization: Optional[str],
    jenis_pemeriksaan: str,
    anatomical_area: str,
    tujuan_analisis: str,
    diagnosis_code_system: str,
    frame_label: str,
    llm_synthesis: bool = False,
    mode_pindai: str = "anatomi_lesi",
):
    model_lower = model_name.lower()
    mode_pindai = ai_parsers.normalize_mode(mode_pindai)
    t_start = time.time()
    log: List[str] = []
    anatomical_area = (anatomical_area or "").strip() or "Thorax / Chest"   # aplikasi ini berfokus pada toraks

    def step(msg: str):
        log.append(f"[{time.time() - t_start:5.1f}s] {msg}")

    step(f"Saving & preparing the image: {file.filename}")
    try:
        stored_filename, preview_filename, is_dicom, base64_image = save_uploaded_file(
            file.filename, file_bytes
        )
    except DicomReadError as e:
        raise HTTPException(status_code=422, detail=f"{file.filename}: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process the image file ({file.filename}): {e}")
    step(("DICOM converted to JPEG" if is_dicom else "Image ready") + f" ({len(base64_image) * 3 // 4 // 1024} KB)")

    clinical_context = _get_clinical_context(db, patient_id)
    if clinical_context:
        step("Patient Clinical History included as context")
    scan_meta = {
        "Examination Type": jenis_pemeriksaan,
        "Anatomical Area": anatomical_area,
        "Scan Object": ai_parsers.MODE_LABEL[mode_pindai],
    }

    preview_path = os.path.join(settings.UPLOAD_DIR, preview_filename)
    # Skala tetap untuk AI: citra yang dikirim di-resize (sisi panjang 1024) dan ukurannya dipakai prompt + parser.
    base64_image, img_wh = prepare_ai_image(base64_image)
    if img_wh is None:
        try:
            with Image.open(preview_path) as _im:
                img_wh = _im.size
        except Exception:
            img_wh = None
    if img_wh:
        step(f"Image for the AI scaled to a fixed size: {img_wh[0]} x {img_wh[1]} px (coordinates normalised 0..1)")

    fov = content_bbox(base64_image)
    if fov:
        step(f"Image field of view (non-black area): x {fov[0]:.2f}-{fov[2]:.2f}, y {fov[1]:.2f}-{fov[3]:.2f}; structures outside this area are rejected")

    if llm_synthesis and (diagnosis_code_system or "auto") == "auto":
        diagnosis_code_system = "icd11"

    system_prompt = ai_parsers.build_dynamic_system_prompt(
        model_lower,
        tujuan_analisis=tujuan_analisis,
        diagnosis_code_system=diagnosis_code_system,
        scan_meta=scan_meta,
        clinical_context=clinical_context,
        synthesis_block=ai_parsers.build_synthesis_block(llm_synthesis),
        img_wh=img_wh,
        mode_pindai=mode_pindai,
        fov=fov,
        stage="detect",           # panggilan 1 dari 2: deteksi objek saja (kotak + diagnosis); kontur lewat tombol Segmentasi
    )
    step(f"Call 1 of 2 (object detection only): prompt built ({len(system_prompt)} characters) - scan object={ai_parsers.MODE_LABEL[mode_pindai]}, "
         f"imaging={jenis_pemeriksaan or '-'}, code={diagnosis_code_system or 'auto'}, area={anatomical_area or '-'}"
         + (", SOAP+ICD-11 synthesis" if llm_synthesis else ""))

    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": system_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                    },
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": detect_max_tokens_for(model_name),   # minimal 8000; model "thinking" memakai sebagian token untuk bernalar (batas lebih besar, lihat config.py)
        "stream": False,
    }

    is_claude = 'claude' in model_lower
    if not is_claude and ('gpt' in model_lower or 'gemini' in model_lower):
        payload["response_format"] = {"type": "json_object"}

    headers = {"Content-Type": "application/json"}
    authorization = resolve_authorization(authorization)
    if authorization:
        headers["Authorization"] = authorization

    history_item = models.ScanHistory(
        patient_id=patient_id,
        original_filename=file.filename,
        stored_filename=stored_filename,
        preview_filename=preview_filename,
        is_dicom=1 if is_dicom else 0,
        model_used=model_name,
        jenis_pemeriksaan=jenis_pemeriksaan or "",
        anatomical_area=anatomical_area or "",
        tujuan_analisis=tujuan_analisis or "otomatis",
        diagnosis_code_system=diagnosis_code_system or "auto",
        frame_label=frame_label or "",
        mode_pindai=mode_pindai,
    )

    try:
        step(f"Sending to the AI router: {model_name} (max_tokens {payload['max_tokens']})")
        t_req = time.time()
        async with httpx.AsyncClient(timeout=150) as client:
            response = await _call_router(client, payload, headers, step)

            if response.status_code != 200:
                step(f"Router replied HTTP {response.status_code}")
                history_item.status = "error"
                history_item.error_message = f"HTTP {response.status_code}: {response.text[:500]}"
                db.add(history_item)
                db.commit()
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Error from the AI router ({file.filename}): {response.text[:300]}",
                )

            step(f"Response received ({time.time() - t_req:.1f}s, {len(response.content) // 1024 or 1} KB)")
            try:
                response_data = response.json()
            except ValueError:
                raise ValueError(f"The router returned a non-JSON response: {_post_payload_sync_note(response.text)}")
            message, finish_reason = _message_from_response(response_data)
            raw_content = ai_parsers.extract_message_text(message)
            if finish_reason == "length":
                step("Warning: model output was truncated (token limit) - trying to repair the JSON")

            parsed_result, parse_mode = None, "none"
            raw_obj, parse_mode = ai_parsers.parse_with_mode(raw_content)
            if isinstance(raw_obj, dict):
                parsed_result = ai_parsers.normalize_result(raw_obj, img_wh, model_lower, fov)
                step(f"JSON parsed successfully (mode: {parse_mode})")
            else:
                step(f"JSON unreadable ({parse_mode}); asking the model to tidy its output…")
                if raw_content and raw_content.strip():
                    repair_payload = {
                        "model": model_name,
                        "messages": [{"role": "user", "content": ai_parsers.REPAIR_PROMPT + ai_parsers._strip_reasoning(raw_content)[:6000]}],
                        "temperature": 0.0, "max_tokens": 6000 if is_thinking_model(model_name) else 3000, "stream": False,
                    }
                    repair_error = None
                    try:
                        rr = await client.post(settings.NINEROUTER_URL, json=repair_payload, headers=headers)
                        if rr.status_code == 200:
                            rmsg, _ = _message_from_response(rr.json())
                            rtext = ai_parsers.extract_message_text(rmsg)
                            if ai_parsers.repair_refused(rtext):
                                repair_error = "model repair menyatakan teks asal bukan analisis radiologi"
                            else:
                                robj, rmode = ai_parsers.parse_with_mode(rtext)
                                if isinstance(robj, dict) and robj.get("error"):
                                    repair_error = f"model repair menandai teks bukan analisis radiologi ({robj['error']})"
                                elif isinstance(robj, dict):
                                    parsed_result = ai_parsers.normalize_result(robj, img_wh, model_lower, fov)
                                    parse_mode = f"repair-llm/{rmode}"
                                    step("JSON recovered through a repair request")
                    except Exception as re_err:  # noqa: BLE001
                        step(f"Repair request failed: {str(re_err)[:100]}")
                    if repair_error:
                        _reject_scan(db, history_item, step, repair_error)
                    if parsed_result is not None:
                        reason = _is_invalid_result(parsed_result, parse_mode)
                        if reason:
                            _reject_scan(db, history_item, step, reason)

        if parsed_result is None:
            parsed_result = ai_parsers.text_fallback_result(raw_content)
            parse_mode = "text_fallback"
            step("The model gave no JSON; using a text summary (no box locations)")
            reason = _is_invalid_result(parsed_result, parse_mode)
            if reason:
                _reject_scan(db, history_item, step, reason)
            parsed_result["needs_review"] = True          # frontend menampilkan banner "Hasil tidak terverifikasi"
        else:
            # jalur JSON utama: tetap tolak jawaban meta / bertanda error (parse_mode non-repair hanya memicu pemeriksaan teks)
            reason = _is_invalid_result(parsed_result, parse_mode)
            if reason:
                _reject_scan(db, history_item, step, reason)
        parsed_result.setdefault("parse_mode", parse_mode)

        # Panggilan 1 hanya untuk deteksi: bila model tetap menulis kontur, buang agar tahap segmentasi (panggilan 2) yang menggambarnya.
        _stray = sum(1 for _a in parsed_result.get("anomalies") or [] if _a.get("polygon")) + sum(
            1 for _s in parsed_result.get("structures") or [] if _s.get("polygon") or _s.get("polyline"))
        for _a in parsed_result.get("anomalies") or []:
            for _k in ("polygon", "centerline", "keypoints"):
                _a.pop(_k, None)
        for _s in parsed_result.get("structures") or []:
            _s.pop("polygon", None)
            _s.pop("polyline", None)
        if _stray:
            step(f"Outlines written by the model in call 1 were discarded ({_stray}); they are drawn in the segmentation call")
        anomalies, removed_devices = ai_parsers.strip_device_findings(parsed_result.get("anomalies", []) or [])
        anomalies, removed_nonlesion = ai_parsers.strip_nonlesion_findings(anomalies)
        if removed_nonlesion:
            step(f"Findings that are soft-tissue overlay or artefact, not lung lesions, were removed: {', '.join(str(x)[:40] for x in removed_nonlesion)}")
        dropped_labels = list(removed_nonlesion)
        # Mode pindai: buang keluaran yang bukan bagian mode terpilih (model kadang tetap mengisi keduanya)
        if not ai_parsers.mode_has_lesion(mode_pindai) and anomalies:
            step(f"Mode {ai_parsers.MODE_LABEL[mode_pindai]}: {len(anomalies)} lesions from the model ignored")
            anomalies = []
        if not ai_parsers.mode_has_anatomy(mode_pindai) and parsed_result.get("structures"):
            step(f"Mode {ai_parsers.MODE_LABEL[mode_pindai]}: anatomical structures from the model ignored")
            parsed_result["structures"] = []
        # Lintasan kedua: tambal temuan yang disebut di teks tanpa kotak, dan ukur CTR (kardiomegali) di kode.
        grounded_structs: list = []
        if ai_parsers.mode_has_lesion(mode_pindai) and settings.GROUNDING_PASS and parse_mode != "text_fallback":
            async def _post_grounding(_payload):
                async with httpx.AsyncClient(timeout=150) as _gc:
                    return await _call_router(_gc, _payload, headers, step)
            step("Grounding pass: localising findings that have no box and measuring the cardiothoracic ratio")
            _gtok = settings.GROUNDING_MAX_TOKENS_THINKING if is_thinking_model(model_name) else settings.GROUNDING_MAX_TOKENS
            grounded, _missing, _gerr = await ai_parsers.run_grounding_pass(
                _post_grounding, model_name, base64_image, parsed_result, anomalies, img_wh, model_lower, fov, _gtok)
            for _m in _missing:
                step(f"  named in the diagnosis but not boxed in the first pass: {_m['text']}")
            if _gerr:
                step(f"  grounding pass unavailable ({_gerr}); first-pass results are used as they are")
            else:
                for _n in ai_parsers.merge_grounded(anomalies, grounded, _missing):
                    step(f"  {_n}")
                _ctr = ai_parsers.compute_ctr(grounded, ai_parsers.grounding._gray_array(base64_image))
                if _ctr:
                    step(f"  CTR {_ctr['ctr']:.2f} (heart {_ctr['lebar_jantung']:.2f} / thorax {_ctr['lebar_toraks']:.2f}, {_ctr['sumber']}): {_ctr['kategori']}")
                    _cn = ai_parsers.apply_ctr(parsed_result, anomalies, _ctr)
                    if _cn:
                        step(f"  {_cn}")
                else:
                    step("  CTR could not be measured (heart/thorax landmarks missing or implausible)")
                grounded_structs = ai_parsers.lung_structures(grounded, (_ctr or {}).get("box_jantung"))
                if grounded_structs:
                    step(f"  lung fields from the grounding pass used as location evidence: {', '.join(s_['taxon'] for s_ in grounded_structs)}")
        _before = len(anomalies)
        _with_box = sum(1 for a in anomalies if a.get("box"))
        anomalies = ai_parsers.sanitize_anomaly_geometry(anomalies)
        _after_box = sum(1 for a in anomalies if a.get("box"))
        if _before:
            step(f"Boxes from the model: {_with_box}/{_before}, passed validation: {_after_box}/{_before}")
            for _a in anomalies:
                _b = _a.get("box")
                if _b:
                    step("  box " + str(_a.get("label", ""))[:28] + f": x {_b['xmin']:.2f}-{_b['xmax']:.2f}, y {_b['ymin']:.2f}-{_b['ymax']:.2f}")
        step(f"Abnormalities detected: {len(anomalies)}" + (f" (medical devices ignored: {len(removed_devices)})" if removed_devices else ""))
        for _n in parsed_result.pop("_struct_notes", []) or []:
            step(f"  taxonomy: {_n}")
        structures = ai_parsers.sanitize_structures(parsed_result.get("structures") or [])
        structures, _anat_notes, _struct_dropped = ai_parsers.reconcile_structures_ex(structures, fov)
        for _n in _anat_notes:
            step(f"  anatomy correction: {_n}")
        if _struct_dropped:
            step("  structures dropped: " + "; ".join(f"{d['label']} ({d['alasan']})" for d in _struct_dropped))
        _s_box = sum(1 for st in structures if st.get("box") and not st.get("derived"))
        step(f"Object detection: {_after_box} lesion boxes + {_s_box} anatomy boxes; segmentation not run yet (press Segmentation for call 2 of 2)")
        if structures:
            step("  structures (taxonomy ids): " + ", ".join(st["taxon"] for st in structures if not st.get("derived")))
        elif ai_parsers.mode_has_anatomy(mode_pindai):
            step("  The model gave no valid thoracic structures (anatomy segmentation layer is empty)")
        if anomalies:
            step("  lesion severity: " + ", ".join(
                f"{str(a.get('label', ''))[:24]}={a.get('severity_score', 0):.2f}" for a in anomalies))

        _n_in = len(anomalies)
        for _n in ai_parsers.refine_anomaly_geometry(anomalies, structures or grounded_structs, fov):
            step(f"  lesion correction: {_n}")
        _bad = [a for a in anomalies if a.get("_drop")]
        if _bad:
            dropped_labels += [str(a.get("label") or a.get("id") or "lesion") for a in _bad]
            anomalies = [a for a in anomalies if not a.get("_drop")]
            step(f"  lesions removed because the location was invalid: {len(_bad)}")
        step(f"  lesions: {_n_in} after filtering, {len(anomalies)} shown after location check")
        _, _landmark = midline_x(structures, fov)
        _lat = ai_parsers.align_text_laterality(parsed_result, anomalies, landmark=_landmark)
        if _lat:
            step(f"  {_lat}")
        if anomalies:
            step("  lesion anatomical location: " + "; ".join(f"{str(a.get('label', ''))[:22]} -> {a.get('lokasi_label') or '-'}" for a in anomalies))
        parsed_result["anomalies"] = anomalies
        _sync = ai_parsers.sync_diagnosis_with_findings(parsed_result, anomalies, dropped_labels)
        if _sync:
            step(f"Diagnosis synchronised with the validated findings: {_sync}")
        parsed_result, _recon = ai_parsers.reconcile_thorax_diagnosis(parsed_result)
        if _recon:
            step(f"Diagnosis consistency correction: {_recon}")

        structures = [st for st in structures if not st.get("derived")]    # zona paru diturunkan dari KONTUR paru, jadi baru dibuat setelah segmentasi
        parsed_result["anomalies"] = anomalies
        parsed_result["structures"] = structures
        if _struct_dropped:
            parsed_result["structures_dibuang"] = _struct_dropped     # ditampilkan di UI: "Struktur dibuang: ..."
        parsed_result["mode_pindai"] = mode_pindai
        parsed_result["stage"] = "detect"
        parsed_result["segmented"] = False
        if fov:
            parsed_result["fov"] = list(fov)
        parsed_result["jenis_pemeriksaan"] = jenis_pemeriksaan or ""
        if removed_devices:
            parsed_result["devices_noted"] = removed_devices

        history_item.status = "success"
        history_item.diagnosis = parsed_result.get("diagnosis", "") or ""
        history_item.confidence = float(parsed_result.get("confidence", 0) or 0)
        history_item.summary = parsed_result.get("summary", "") or ""
        history_item.anomalies_json = json.dumps(anomalies)
        history_item.structures_json = json.dumps(structures)
        history_item.segmented = 0
        history_item.diagnosis_code = parsed_result.get("diagnosis_code", "") or ""
        if parsed_result.get("diagnosis_code_system"):
            history_item.diagnosis_code_system = str(parsed_result.get("diagnosis_code_system"))

        db.add(history_item)
        db.commit()
        db.refresh(history_item)
        step(f"Done & saved to history (total {time.time() - t_start:.1f}s)")

        return {
            "status": "success",
            "data": parsed_result,
            "history": _to_out(history_item),
            "log": log,
        }

    except httpx.RequestError as e:
        step(f"Connection failed: {e}")
        history_item.status = "error"
        history_item.error_message = f"Failed to connect to the AI router: {e}"
        db.add(history_item)
        db.commit()
        raise HTTPException(status_code=502, detail=f"Failed to connect to the AI router: {e}")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        step(f"Error: {e}")
        history_item.status = "error"
        history_item.error_message = str(e)
        db.add(history_item)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")


@router.post("/scan")
async def scan_medical_image(
    file: UploadFile = File(...),
    model: str = Form("kr/claude-sonnet-4.5"),
    patient_id: Optional[int] = Form(None),
    authorization: Optional[str] = Form(None),
    jenis_pemeriksaan: str = Form(""),
    anatomical_area: str = Form(""),
    tujuan_analisis: str = Form("otomatis"),
    diagnosis_code_system: str = Form("auto"),
    frame_label: str = Form(""),
    llm_synthesis: bool = Form(False),
    mode_pindai: str = Form("anatomi_lesi"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    model_name = strip_low(model)

    if patient_id:
        patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
        if not patient:
            raise HTTPException(status_code=400, detail="Target patient not found.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="The file is empty or could not be read.")

    return await _run_single_scan(
        db, file, file_bytes, model_name, patient_id, authorization,
        jenis_pemeriksaan, anatomical_area, tujuan_analisis,
        diagnosis_code_system, frame_label, llm_synthesis, mode_pindai,
    )


@router.post("/scan/batch")
async def scan_medical_images_batch(
    files: List[UploadFile] = File(...),
    frame_labels: str = Form("[]"),  # JSON array of labels, sejajar urutan files
    model: str = Form("kr/claude-sonnet-4.5"),
    patient_id: Optional[int] = Form(None),
    authorization: Optional[str] = Form(None),
    jenis_pemeriksaan: str = Form(""),
    anatomical_area: str = Form(""),
    tujuan_analisis: str = Form("otomatis"),
    diagnosis_code_system: str = Form("auto"),
    llm_synthesis: bool = Form(False),
    mode_pindai: str = Form("anatomi_lesi"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Memindai beberapa citra sekaligus (mode multi-frame di UI), mengembalikan hasil per berkas
    dalam urutan yang sama. Kegagalan pada satu berkas tidak menghentikan berkas lain."""
    model_name = strip_low(model)

    if patient_id:
        patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
        if not patient:
            raise HTTPException(status_code=400, detail="Target patient not found.")

    try:
        labels = json.loads(frame_labels) if frame_labels else []
    except json.JSONDecodeError:
        labels = []

    results = []
    for idx, f in enumerate(files):
        label = labels[idx] if idx < len(labels) else f"Frame {idx + 1}"
        try:
            fb = await f.read()
            if not fb:
                results.append({"status": "error", "detail": "Empty file.", "frame_label": label})
                continue
            result = await _run_single_scan(
                db, f, fb, model_name, patient_id, authorization,
                jenis_pemeriksaan, anatomical_area, tujuan_analisis,
                diagnosis_code_system, label, llm_synthesis, mode_pindai,
            )
            result["frame_label"] = label
            results.append(result)
        except HTTPException as e:
            results.append({"status": "error", "detail": str(e.detail), "frame_label": label})
        except Exception as e:
            results.append({"status": "error", "detail": str(e), "frame_label": label})

    return {"results": results}


# ======================================================================
#  Panggilan 2 dari 2: Segmentasi (tombol "Segmentasi" di UI)
# ======================================================================
async def _run_segmentation(db: Session, item: models.ScanHistory, model_name: str, authorization: Optional[str]):
    """Gambar kontur untuk objek yang sudah dideteksi pada panggilan 1. Kotak tidak diubah; hanya polygon/polyline yang ditambahkan."""
    import base64
    t_start = time.time()
    log: List[str] = []

    def step(msg: str):
        log.append(f"[{time.time() - t_start:5.1f}s] {msg}")

    try:
        anomalies = json.loads(item.anomalies_json or "[]")
    except json.JSONDecodeError:
        anomalies = []
    structures = _structures_of(item)
    if not isinstance(anomalies, list):
        anomalies = []
    n_les, n_str = len(ai_parsers.pick_lesions(anomalies)), len(ai_parsers.pick_structures(structures))
    if not n_les and not n_str:
        raise HTTPException(status_code=400, detail="No detected (boxed) objects to segment. Run object detection first.")

    fpath = os.path.join(settings.UPLOAD_DIR, item.preview_filename or item.stored_filename or "")
    if not os.path.isfile(fpath):
        raise HTTPException(status_code=404, detail="Image file not found on the server.")
    with open(fpath, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("utf-8")
    b64, img_wh = prepare_ai_image(b64)
    if img_wh is None:
        try:
            with Image.open(fpath) as _im:
                img_wh = _im.size
        except Exception:
            img_wh = None
    fov = content_bbox(b64)
    step(f"Call 2 of 2 (segmentation): {n_les} lesion boxes + {n_str} anatomy boxes from call 1 to outline")

    prompt = ai_parsers.build_segmentation_prompt(anomalies, structures, img_wh, fov)
    step(f"Prompt built ({len(prompt)} characters)")
    model_lower = model_name.lower()
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
        "temperature": 0.0,
        "max_tokens": segment_max_tokens_for(model_name),     # minimal 8000
        "stream": False,
    }
    if "claude" not in model_lower and ("gpt" in model_lower or "gemini" in model_lower):
        payload["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    authorization = resolve_authorization(authorization)
    if authorization:
        headers["Authorization"] = authorization

    try:
        step(f"Sending to the AI router: {model_name} (max_tokens {payload['max_tokens']})")
        t_req = time.time()
        async with httpx.AsyncClient(timeout=180) as client:
            response = await _call_router(client, payload, headers, step)
        if response.status_code != 200:
            step(f"Router replied HTTP {response.status_code}")
            raise HTTPException(status_code=response.status_code, detail=f"Error from the AI router (segmentation): {response.text[:300]}")
        step(f"Response received ({time.time() - t_req:.1f}s, {len(response.content) // 1024 or 1} KB)")
        try:
            response_data = response.json()
        except ValueError:
            raise ValueError(f"The router returned a non-JSON response: {_post_payload_sync_note(response.text)}")
        message, finish_reason = _message_from_response(response_data)
        raw_content = ai_parsers.extract_message_text(message)
        if finish_reason == "length":
            step("Warning: model output was truncated (token limit) - repairing the JSON, outlines that were cut off are skipped")
    except httpx.RequestError as e:
        step(f"Connection failed: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to the AI router: {e}")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        step(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

    obj, mode = ai_parsers.parse_segmentation_json(raw_content)
    if not isinstance(obj, dict):
        step(f"Segmentation output unreadable ({mode})")
        raise HTTPException(status_code=502, detail="The model's segmentation output could not be read. Detection results are unchanged; press Segmentation again or choose another model.")
    les_out, str_out = ai_parsers.extract_outlines(obj, img_wh, model_lower)
    step(f"JSON parsed (mode: {mode}): outlines for {len(les_out)} lesions + {len(str_out)} anatomy objects")
    if not les_out and not str_out:
        raise HTTPException(status_code=502, detail="The model returned no contours. Detection results are unchanged; try again or choose another model.")

    ai_parsers.merge_outlines(anomalies, structures, les_out, str_out)
    anomalies = ai_parsers.sanitize_anomaly_geometry(anomalies)          # kontur yang keluar dari kotaknya dibuang
    structures = ai_parsers.sanitize_structures([s for s in structures if not s.get("derived")])
    structures, _notes, _dropped = ai_parsers.reconcile_structures_ex(structures, fov)   # sisi kiri/kanan, garis tengah, zona paru dari kontur paru
    for _n in _notes:
        step(f"  anatomy correction: {_n}")
    _boxes = {id(a): (dict(a["box"]), dict(a["pointer"]) if isinstance(a.get("pointer"), dict) else None) for a in anomalies if isinstance(a.get("box"), dict)}
    for _n in ai_parsers.refine_anomaly_geometry(anomalies, structures, fov):
        step(f"  lesion correction: {_n}")
    for _a in anomalies:
        _a.pop("_drop", None)          # lesi sudah divalidasi pada panggilan 1; panggilan 2 tidak membuang lesi
        if id(_a) in _boxes:           # kotak hasil panggilan 1 final: panggilan 2 hanya menambah kontur
            _a["box"] = _boxes[id(_a)][0]
            if _boxes[id(_a)][1]:
                _a["pointer"] = _boxes[id(_a)][1]
    n_poly = sum(1 for a in anomalies if a.get("polygon"))
    n_sp = sum(1 for s in structures if (s.get("polygon") or s.get("polyline")) and not s.get("derived"))
    step(f"Segmentation: {n_poly} lesion outlines (heatmap) + {n_sp} anatomy outlines/lines kept after validation")

    item.anomalies_json = json.dumps(anomalies)
    item.structures_json = json.dumps(structures)
    item.segmented = 1 if ai_parsers.is_segmented(anomalies, structures) else 0
    db.add(item)
    db.commit()
    db.refresh(item)
    step(f"Done & saved to history (total {time.time() - t_start:.1f}s)")
    return {
        "status": "success",
        "data": {"anomalies": anomalies, "structures": structures, "segmented": bool(item.segmented), "stage": "segment",
                 "mode_pindai": item.mode_pindai or "anatomi_lesi", **({"fov": list(fov)} if fov else {})},
        "history": _to_out(item),
        "log": log,
    }


@router.post("/scan/{history_id}/segment")
async def segment_scan(
    history_id: int,
    model: str = Form(""),
    authorization: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Panggilan 2 dari 2: segmentasi untuk hasil deteksi yang sudah tersimpan (history_id)."""
    item = db.query(models.ScanHistory).filter(models.ScanHistory.id == history_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="History not found.")
    if item.status != "success":
        raise HTTPException(status_code=400, detail="This scan was unsuccessful, so there are no objects to segment.")
    model_name = strip_low(model) if (model or "").strip() else (item.model_used or "")
    if not model_name:
        raise HTTPException(status_code=400, detail="No AI model selected.")
    return await _run_segmentation(db, item, model_name, authorization)
