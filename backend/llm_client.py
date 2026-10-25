"""Utilitas bersama untuk fitur yang memanggil router AI dengan keluaran JSON bebas skema
(Insight temuan, Profil Klinis, Care Plan, kode diagnosis).

Seluruh pemanggilan memakai router yang sama dengan Pemindaian AI (NINEROUTER_URL),
sehingga API key dari kolom sidebar / .env tetap berlaku.
"""
import json
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

import ai_parsers
import models
from config import settings, resolve_authorization

logger = logging.getLogger(__name__)


def strip_low(model: str) -> str:
    """Buang sufiks '(low)' dari semua model. Sufiks itu hanya label di dropdown UI; bila ikut terkirim,
    Google/router menolak dengan 400 'unexpected model name format'."""
    return (model or "").replace("(low)", "").strip()


def parse_json_any(raw_content) -> Optional[Any]:
    """Ambil objek/array JSON terbesar dari keluaran model (toleran terhadap <think>, pagar kode, JSON longgar)."""
    raw = ai_parsers.extract_text(raw_content)
    if not raw or not raw.strip():
        return None
    text = ai_parsers._strip_reasoning(raw)
    if not text:
        text = raw
    obj, _ = ai_parsers._try_load(text) if text.lstrip()[:1] in "{[" else (None, None)
    if isinstance(obj, (dict, list)) and obj:
        return obj
    best, best_len = None, 0
    for cand in ai_parsers._iter_json_objects(text):
        o, _m = ai_parsers._try_load(cand)
        if isinstance(o, dict) and len(cand) > best_len:
            best, best_len = o, len(cand)
    if best is not None:
        return best
    # array di tingkat atas yang didahului teks
    i, j = text.find("["), text.rfind("]")
    if i != -1 and j > i:
        o, _m = ai_parsers._try_load(text[i:j + 1])
        if isinstance(o, list):
            return o
    return None


_JSON_REPAIR_PROMPT = (
    "Teks berikut adalah jawaban AI yang seharusnya berupa SATU objek JSON tetapi rusak atau terpotong. "
    "Ubah menjadi SATU objek JSON valid dengan struktur dan isi yang sama persis; jangan menambah isi baru dan "
    "jangan meringkas. Balas HANYA JSON mentah tanpa markdown.\n\nTEKS:\n"
)


def _finish_reason(data: Any) -> Optional[str]:
    try:
        return (data.get("choices") or [{}])[0].get("finish_reason")
    except Exception:
        return None


async def _post_router(client: httpx.AsyncClient, payload: Dict[str, Any], headers: Dict[str, str]) -> httpx.Response:
    """POST ke router AI. Bila router menolak `response_format` (HTTP 400/422), ulangi sekali tanpa field itu."""
    resp = await client.post(settings.NINEROUTER_URL, json=payload, headers=headers)
    if resp.status_code in (400, 422) and "response_format" in payload:
        payload.pop("response_format", None)
        resp = await client.post(settings.NINEROUTER_URL, json=payload, headers=headers)
    return resp


async def chat_json(
    prompt: str,
    model: str,
    authorization: Optional[str] = None,
    max_tokens: int = 3500,
    timeout: float = 150,
    retries: int = 2,
) -> Any:
    """Kirim prompt teks ke router AI dan kembalikan JSON hasil parse. Melempar HTTPException bila gagal.

    Penguatan terhadap model 'thinking' (mis. Gemini Flash): token bernalar memakan jatah max_tokens sehingga
    'content' kosong atau JSON terpotong. Ditangani dengan: response_format json_object (non-Claude),
    pesan system 'hanya JSON', jatah token dinaikkan saat finish_reason == length, dan satu putaran
    perbaikan oleh model bila teks ada tetapi tidak bisa diparse.
    """
    model_name = strip_low(model or "kr/claude-sonnet-4.5").strip()
    model_lower = model_name.lower()
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "Reply with ONLY one valid JSON object. No markdown, no introductory or closing text. Write all free-text values in English (keep JSON keys and enumerated values exactly as specified)."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if "claude" not in model_lower:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    auth = resolve_authorization(authorization)
    if auth:
        headers["Authorization"] = auth

    last_err = "The AI response could not be read as JSON."
    last_raw = ""
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await _post_router(client, payload, headers)
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=f"Error dari router AI: {resp.text[:300]}")
                try:
                    data = resp.json()
                except ValueError:
                    last_err = f"Router mengembalikan respons non-JSON: {(resp.text or '')[:200]}"
                    continue
                choices = data.get("choices") if isinstance(data, dict) else None
                if not choices:
                    err = data.get("error") if isinstance(data, dict) else None
                    last_err = f"Router mengembalikan error: {ai_parsers.extract_text(err)[:300]}" if err else "Respons model tidak valid (tanpa choices)."
                    continue
                message = (choices[0] or {}).get("message") or {}
                finish = _finish_reason(data)
                raw_text = ai_parsers.extract_message_text(message)
                parsed = parse_json_any(raw_text)
                if parsed is None:
                    for k in ("reasoning_content", "reasoning", "thinking"):
                        parsed = parse_json_any(message.get(k))
                        if parsed is not None:
                            break
                if parsed is not None:
                    return parsed

                # Teks ada tetapi tidak bisa diparse: minta model merapikannya jadi JSON (sekali per percobaan).
                clean = ai_parsers._strip_reasoning(raw_text or "")
                last_raw = clean
                if len(clean.strip()) > 40 and finish != "length":
                    rp = {
                        "model": model_name,
                        "messages": [{"role": "user", "content": _JSON_REPAIR_PROMPT + clean[:12000]}],
                        "temperature": 0.0,
                        "max_tokens": min(int(payload["max_tokens"]), 12000),
                        "stream": False,
                    }
                    if "claude" not in model_lower:
                        rp["response_format"] = {"type": "json_object"}
                    try:
                        r2 = await _post_router(client, rp, headers)
                        if r2.status_code == 200:
                            d2 = r2.json()
                            m2 = ((d2.get("choices") or [{}])[0] or {}).get("message") or {}
                            fixed = parse_json_any(ai_parsers.extract_message_text(m2))
                            if fixed is not None:
                                return fixed
                    except (httpx.RequestError, ValueError):
                        pass

                snippet = re.sub(r"\s+", " ", clean).strip()[:160]
                reason = {
                    "length": "keluaran terpotong karena batas token (model 'thinking' memakai jatah token untuk bernalar)",
                    "content_filter": "keluaran diblokir filter konten router",
                }.get(finish or "", f"finish_reason={finish or '-'}")
                last_err = (
                    f"Model tidak mengembalikan JSON yang valid ({reason}). "
                    + (f"Awal respons: \"{snippet}\"" if snippet else "Isi respons kosong.")
                )
                logger.warning("chat_json gagal (model=%s, attempt=%d, finish=%s, max_tokens=%s): %r",
                               model_name, attempt + 1, finish, payload["max_tokens"], (raw_text or "")[:400])
                # Naikkan jatah token bila terpotong atau kosong (indikasi token habis untuk bernalar).
                if finish == "length" or not clean.strip():
                    payload["max_tokens"] = min(int(payload["max_tokens"] * 1.7), 16000)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Gagal terhubung ke router AI: {e}")
    raise HTTPException(status_code=502, detail=last_err)


# ---------------------------------------------------------------- konteks pasien

def _age_years(birth_date: str) -> Optional[int]:
    if not birth_date:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            b = datetime.strptime(birth_date.strip(), fmt).date()
            today = date.today()
            return today.year - b.year - ((today.month, today.day) < (b.month, b.day))
        except ValueError:
            continue
    return None


def patient_age(patient: Optional[models.Patient]) -> Optional[int]:
    return _age_years(patient.birth_date) if patient else None


def load_profile_dict(db: Session, patient_id: int) -> Dict[str, Any]:
    row = db.query(models.ClinicalProfile).filter(models.ClinicalProfile.patient_id == patient_id).first()
    if not row:
        return {}
    try:
        data = json.loads(row.data_json or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def summarize_profile(profile: Dict[str, Any]) -> str:
    """Ringkasan teks Profil Klinis terstruktur untuk disuntikkan ke prompt."""
    if not profile:
        return ""
    lines: List[str] = []
    for d in profile.get("diagnoses", []) or []:
        kodes = d.get("kodes") or {}
        kode = "; ".join(f"{k}={v.get('kode')}" for k, v in kodes.items() if isinstance(v, dict) and v.get("kode"))
        parts = [d.get("nama", ""), d.get("severity", ""), d.get("status_kontrol", "")]
        lines.append(f"- {d.get('peran', 'komorbid')}: " + " | ".join(p for p in parts if p) + (f" [{kode}]" if kode else ""))
    organ = profile.get("organ") or {}
    units = {"ecog": "ECOG", "egfr": "eGFR mL/min", "gds": "GDS mg/dL", "lvef": "LVEF %", "sgot": "SGOT U/L", "sgpt": "SGPT U/L", "hb": "Hb g/dL"}
    organ_txt = [f"{label} {organ.get(k)}" for k, label in units.items() if organ.get(k) is not None]
    if organ_txt:
        lines.append("Kapasitas organ: " + "; ".join(organ_txt))
    skor = profile.get("skor") or {}
    if skor.get("cci_nilai") is not None:
        lines.append(f"Charlson Comorbidity Index: {skor.get('cci_nilai')}")
    haz = [h.get("judul") for h in (profile.get("hazards") or []) if h.get("judul") and not h.get("override")]
    if haz:
        lines.append("Bahaya klinis aktif: " + "; ".join(haz))
    return "\n".join(lines)


def clinical_text(db: Session, patient_id: int) -> str:
    ch = db.query(models.ClinicalHistory).filter(models.ClinicalHistory.patient_id == patient_id).first()
    if not ch:
        return ""
    labels = {
        "identitas_pasien": "Identitas Pasien", "keluhan_utama": "Keluhan Utama", "pemeriksaan_fisik": "Pemeriksaan Fisik",
        "pemeriksaan_penunjang": "Pemeriksaan Penunjang", "riwayat_medis": "Riwayat Medis", "keterangan_lainnya": "Keterangan Lainnya",
    }
    parts = []
    for f, lab in labels.items():
        v = (getattr(ch, f, "") or "").strip()
        if v:
            parts.append(f"{lab}: {v}")
    return "\n".join(parts)


def latest_scans_text(db: Session, patient_id: int, limit: int = 3) -> str:
    items = (
        db.query(models.ScanHistory)
        .filter(models.ScanHistory.patient_id == patient_id, models.ScanHistory.status == "success")
        .order_by(models.ScanHistory.created_at.desc())
        .limit(limit)
        .all()
    )
    lines = []
    for it in items:
        try:
            anomalies = json.loads(it.anomalies_json or "[]")
        except json.JSONDecodeError:
            anomalies = []
        temuan = "; ".join(
            f"{a.get('label', 'Kelainan')} ({a.get('severity', '-')})" for a in anomalies[:6] if isinstance(a, dict)
        )
        kode = f" [{it.diagnosis_code}]" if getattr(it, "diagnosis_code", "") else ""
        lines.append(
            f"- {it.created_at:%Y-%m-%d} {it.jenis_pemeriksaan or 'pencitraan'} {it.anatomical_area or ''}: "
            f"{it.diagnosis or '-'}{kode}. Ringkasan: {(it.summary or '-')[:300]}. Temuan: {temuan or '-'}"
        )
    return "\n".join(lines)


def build_patient_context(db: Session, patient_id: Optional[int], include_scans: bool = True, include_profile: bool = True) -> str:
    """Konteks lengkap pasien untuk prompt (data demografis, riwayat klinis, profil terstruktur, pemindaian terbaru)."""
    if not patient_id:
        return ""
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        return ""
    blocks = []
    demo = [f"Nama: {patient.name}"]
    if patient.gender:
        demo.append("Jenis kelamin: " + ("Laki-laki" if patient.gender == "L" else "Perempuan" if patient.gender == "P" else patient.gender))
    age = patient_age(patient)
    if age is not None:
        demo.append(f"Usia: {age} tahun")
    if (patient.notes or "").strip():
        demo.append(f"Catatan klinis: {patient.notes.strip()[:400]}")
    blocks.append("DATA PASIEN:\n" + "\n".join(demo))
    ct = clinical_text(db, patient_id)
    if ct:
        blocks.append("RIWAYAT KLINIS:\n" + ct[:6000])
    if include_profile:
        ps = summarize_profile(load_profile_dict(db, patient_id))
        if ps:
            blocks.append("PROFIL KLINIS TERSTRUKTUR:\n" + ps)
    if include_scans:
        st = latest_scans_text(db, patient_id)
        if st:
            blocks.append("PEMINDAIAN TERBARU:\n" + st)
    return "\n\n".join(blocks)


DISCLAIMER_RULES = (
    "ATURAN: Gunakan hanya data yang tersedia di konteks. Jangan mengarang nilai laboratorium, usia, atau riwayat yang "
    "tidak disebutkan. Bila data tidak cukup, tulis bahwa data belum tersedia. Keluaran adalah dukungan keputusan "
    "yang harus ditinjau tenaga medis, bukan keputusan klinis final. Write all free-text values in English. "
    "Jangan memakai tanda pisah panjang atau tanda pisah sedang, dan jangan memakai emoji."
)


def scrub(obj: Any) -> Any:
    """Bersihkan keluaran AI secara rekursif: ganti tanda pisah panjang/sedang dengan tanda hubung biasa."""
    if isinstance(obj, str):
        return obj.replace("\u2014", "-").replace("\u2013", "-").strip()
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    return obj
