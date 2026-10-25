from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

import ai_parsers
import models
from llm_client import strip_low
import schemas
from config import settings, resolve_authorization
from database import get_db
from security import get_current_user

router = APIRouter(prefix="/api/clinical-history", tags=["Clinical History"])

FIELD_LABELS = {
    "identitas_pasien": "Identitas Pasien",
    "keluhan_utama": "Keluhan Utama",
    "pemeriksaan_fisik": "Pemeriksaan Fisik",
    "pemeriksaan_penunjang": "Pemeriksaan Penunjang",
    "riwayat_medis": "Riwayat Medis",
    "keterangan_lainnya": "Keterangan Lainnya",
}


def _get_or_create(db: Session, patient_id: int) -> models.ClinicalHistory:
    ch = db.query(models.ClinicalHistory).filter(models.ClinicalHistory.patient_id == patient_id).first()
    if not ch:
        ch = models.ClinicalHistory(patient_id=patient_id)
        db.add(ch)
        db.commit()
        db.refresh(ch)
    return ch


def _extract_text(filename: str, raw: bytes) -> str:
    """Ekstraksi teks sederhana dari berkas yang diunggah (txt langsung; pdf/docx best-effort
    memakai library opsional jika terpasang, jika tidak tersedia fallback decode mentah)."""
    name = (filename or "").lower()
    if name.endswith((".txt", ".md", ".csv")):
        return raw.decode("utf-8", errors="ignore")

    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(raw))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            return raw.decode("utf-8", errors="ignore")

    if name.endswith(".docx"):
        try:
            import docx
            import io
            doc = docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            return raw.decode("utf-8", errors="ignore")

    return raw.decode("utf-8", errors="ignore")


@router.get("/{patient_id}", response_model=schemas.ClinicalHistoryOut)
def get_clinical_history(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
    ch = db.query(models.ClinicalHistory).filter(models.ClinicalHistory.patient_id == patient_id).first()
    if not ch:
        return schemas.ClinicalHistoryOut(patient_id=patient_id)
    return schemas.ClinicalHistoryOut.model_validate(ch)


@router.put("/{patient_id}", response_model=schemas.ClinicalHistoryOut)
def update_clinical_history(
    patient_id: int,
    payload: schemas.ClinicalHistoryUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
    ch = _get_or_create(db, patient_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(ch, key, value or "")
    db.commit()
    db.refresh(ch)
    return schemas.ClinicalHistoryOut.model_validate(ch)


@router.post("/{patient_id}/ai-parse", response_model=schemas.ClinicalHistoryOut)
async def ai_parse_clinical_history(
    patient_id: int,
    files: List[UploadFile] = File(...),
    model: str = Form("kr/claude-sonnet-4.5"),
    authorization: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Mengunggah satu/beberapa dokumen (rekam medis, hasil anamnesis, dsb) lalu meminta AI
    memisahkan otomatis isinya ke enam kategori Clinical History."""
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    combined_text = []
    for f in files:
        raw = await f.read()
        if not raw:
            continue
        text = _extract_text(f.filename, raw)
        combined_text.append(f"--- Berkas: {f.filename} ---\n{text.strip()}")
    full_text = "\n\n".join(combined_text).strip()

    if not full_text:
        raise HTTPException(status_code=400, detail="No text could be extracted from the uploaded files.")

    system_prompt = (
        "Anda adalah asisten rekam medis. Anda akan menerima potongan teks dokumen klinis pasien "
        "(bisa berupa anamnesis, resume medis, hasil lab, dsb). Pisahkan & rangkum isinya ke dalam "
        "ENAM kategori berikut, HANYA balas dengan objek JSON (tanpa markdown):\n"
        "{\n"
        '  "identitas_pasien": "...",\n'
        '  "keluhan_utama": "...",\n'
        '  "pemeriksaan_fisik": "...",\n'
        '  "pemeriksaan_penunjang": "...",\n'
        '  "riwayat_medis": "...",\n'
        '  "keterangan_lainnya": "..."\n'
        "}\n"
        "Jika suatu kategori tidak ada informasinya pada teks, isi dengan string kosong. "
        "Jangan mengarang data yang tidak ada pada teks sumber."
    )

    model_name = strip_low(model)
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": f"{system_prompt}\n\nTEKS DOKUMEN:\n{full_text[:12000]}"}
        ],
        "temperature": 0.0,
        "max_tokens": 1500,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    authorization = resolve_authorization(authorization)
    if authorization:
        headers["Authorization"] = authorization

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(settings.NINEROUTER_URL, json=payload, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Error from the AI router: {response.text[:300]}")
        response_data = response.json()
        raw_content = response_data['choices'][0]['message']['content']
        parsed = ai_parsers.parse_model_response(model_name.lower(), raw_content) or {}
    except HTTPException:
        raise
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to connect to the AI router: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process the AI response: {e}")

    ch = _get_or_create(db, patient_id)
    for field in FIELD_LABELS:
        val = (parsed.get(field, "") or "").strip()
        if val:
            setattr(ch, field, val)
    db.commit()
    db.refresh(ch)
    return schemas.ClinicalHistoryOut.model_validate(ch)
