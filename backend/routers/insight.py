import json
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import llm_client
import models
import schemas
from database import get_db
from insight_catalog import BRANCH_BY_KEY, public_catalog
from security import get_current_user

router = APIRouter(prefix="/api/insight", tags=["Insight Temuan"])


@router.get("/catalog")
def insight_catalog(current_user: models.User = Depends(get_current_user)):
    """Struktur peta opsi hasil pemindaian (7 cabang beserta sub-opsi)."""
    return {"branches": public_catalog()}


def _normalize_items(raw: Any, branch: dict) -> Dict[str, dict]:
    """Pastikan semua sub-opsi cabang ada, dengan bentuk {ringkasan, poin[], tingkat}."""
    items_raw = raw.get("items") if isinstance(raw, dict) else None
    if items_raw is None and isinstance(raw, dict):
        items_raw = raw
    lookup: Dict[str, Any] = {}
    if isinstance(items_raw, dict):
        lookup = {str(k): v for k, v in items_raw.items()}
    elif isinstance(items_raw, list):
        for it in items_raw:
            if isinstance(it, dict):
                k = it.get("key") or it.get("id") or it.get("judul")
                if k:
                    lookup[str(k)] = it

    out: Dict[str, dict] = {}
    for sub in branch["items"]:
        v = lookup.get(sub["key"])
        if v is None:  # cocokkan lewat label bila model memakai label sebagai kunci
            v = next((val for k, val in lookup.items() if k.strip().lower() == sub["label"].lower()), None)
        if isinstance(v, str):
            v = {"ringkasan": v}
        if not isinstance(v, dict):
            out[sub["key"]] = {"ringkasan": "Not enough data for this section.", "poin": [], "tingkat": ""}
            continue
        poin = v.get("poin") or v.get("points") or []
        if isinstance(poin, str):
            poin = [p.strip(" -*") for p in poin.split("\n") if p.strip()]
        out[sub["key"]] = {
            "ringkasan": str(v.get("ringkasan") or v.get("isi") or v.get("summary") or "").strip(),
            "poin": [str(p).strip() for p in poin if str(p).strip()][:8],
            "tingkat": str(v.get("tingkat") or v.get("level") or "").strip(),
        }
    return out


def _build_prompt(req: schemas.InsightRequest, branch: dict, patient_ctx: str) -> str:
    f = req.finding or {}
    box = f.get("box") or {}
    box_txt = ""
    if box:
        try:
            box_txt = (f" Lokasi pada citra (koordinat ternormalisasi): x {float(box.get('xmin', 0)):.2f} sampai {float(box.get('xmax', 0)):.2f}, "
                       f"y {float(box.get('ymin', 0)):.2f} sampai {float(box.get('ymax', 0)):.2f}.")
        except (TypeError, ValueError):
            box_txt = ""
    sub_lines = "\n".join(f'- "{s["key"]}" ({s["label"]}): {s["guide"]}' for s in branch["items"])
    example_keys = ", ".join(f'"{s["key"]}"' for s in branch["items"])
    scan_meta = ", ".join(x for x in (req.jenis_pemeriksaan, req.anatomical_area) if x)
    return (
        "Anda adalah asisten dukungan keputusan klinis untuk tenaga medis. Anda diminta menguraikan SATU cabang analisis "
        f'bernama "{branch["label"]}" untuk satu temuan hasil pemindaian citra medis.\n\n'
        f"TEMUAN TERPILIH: {f.get('label', 'Kelainan')} (tingkat: {f.get('severity', '-')}). "
        f"Deskripsi: {f.get('description', '-')}.{box_txt}\n"
        f"DIAGNOSIS UTAMA PEMINDAIAN: {req.diagnosis or '-'}\n"
        f"RINGKASAN PEMINDAIAN: {req.summary or '-'}\n"
        + (f"JENIS PEMERIKSAAN / AREA: {scan_meta}\n" if scan_meta else "")
        + (f"\n{patient_ctx}\n" if patient_ctx else "\nDATA PASIEN: tidak tersedia (analisis bersifat umum).\n")
        + "\nSUB-OPSI YANG HARUS DIISI (kunci JSON dan arahannya):\n" + sub_lines + "\n\n"
        + "Sesuaikan isi dengan kondisi pasien (usia, komorbid, fungsi organ, riwayat) bila datanya ada di konteks. "
        + llm_client.DISCLAIMER_RULES + "\n\n"
        + "Write ALL free-text values (ringkasan, poin, keterbatasan) in ENGLISH; keep the JSON keys and the \"tingkat\" values exactly as specified. "
        + "Balas HANYA dengan objek JSON tanpa markdown, bentuk:\n"
        + '{"items": {' + ", ".join(f'"{s["key"]}": {{"ringkasan": "2 sampai 4 kalimat", "poin": ["butir singkat", "..."], "tingkat": "Rendah, Sedang, Tinggi, atau kosong"}}' for s in branch["items"]) + "},"
        + ' "keterbatasan": "satu kalimat tentang keterbatasan data"}\n'
        + f"Kunci pada items harus persis: {example_keys}. Maksimal 5 butir pada tiap poin."
    )


@router.post("/generate")
async def generate_insight(
    req: schemas.InsightRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    branch = BRANCH_BY_KEY.get(req.branch)
    if not branch:
        raise HTTPException(status_code=400, detail="Unknown analysis branch.")
    if req.patient_id:
        if not db.query(models.Patient).filter(models.Patient.id == req.patient_id).first():
            raise HTTPException(status_code=400, detail="Patient not found.")

    patient_ctx = llm_client.build_patient_context(db, req.patient_id, include_scans=False)
    prompt = _build_prompt(req, branch, patient_ctx)
    raw = await llm_client.chat_json(prompt, req.model, req.authorization, max_tokens=3000)
    raw = llm_client.scrub(raw)

    result = {
        "branch": branch["key"],
        "label": branch["label"],
        "items": _normalize_items(raw, branch),
        "keterbatasan": str(raw.get("keterbatasan", "")).strip() if isinstance(raw, dict) else "",
        "model": req.model,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "patient_aware": bool(patient_ctx),
    }

    # Simpan ke riwayat pemindaian supaya hasil tidak hilang saat halaman dimuat ulang.
    persisted = False
    if req.history_id is not None and req.anomaly_index is not None:
        item = db.query(models.ScanHistory).filter(models.ScanHistory.id == req.history_id).first()
        if item:
            try:
                anomalies = json.loads(item.anomalies_json or "[]")
            except json.JSONDecodeError:
                anomalies = []
            if 0 <= req.anomaly_index < len(anomalies) and isinstance(anomalies[req.anomaly_index], dict):
                ins = anomalies[req.anomaly_index].setdefault("insights", {})
                ins[branch["key"]] = result
                item.anomalies_json = json.dumps(anomalies)
                db.commit()
                persisted = True
    result["persisted"] = persisted
    return result
