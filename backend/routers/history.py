import json
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import ai_parsers
import models
import schemas
from config import settings
from database import get_db
from security import get_current_user

router = APIRouter(prefix="/api/history", tags=["Riwayat Pemindaian"])


def _structures_of(item) -> list:
    try:
        data = json.loads(getattr(item, "structures_json", "") or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _to_out(item: models.ScanHistory) -> schemas.ScanHistoryOut:
    try:
        anomalies = json.loads(item.anomalies_json or "[]")
    except json.JSONDecodeError:
        anomalies = []

    structures = _structures_of(item)
    return schemas.ScanHistoryOut(
        id=item.id,
        patient_id=item.patient_id,
        patient_name=item.patient.name if item.patient else None,
        original_filename=item.original_filename,
        preview_filename=item.preview_filename,
        is_dicom=item.is_dicom,
        model_used=item.model_used,
        diagnosis=item.diagnosis,
        confidence=item.confidence,
        summary=item.summary,
        anomalies=anomalies,
        status=item.status,
        error_message=item.error_message,
        jenis_pemeriksaan=getattr(item, "jenis_pemeriksaan", "") or "",
        anatomical_area=getattr(item, "anatomical_area", "") or "",
        tujuan_analisis=getattr(item, "tujuan_analisis", "") or "otomatis",
        diagnosis_code_system=getattr(item, "diagnosis_code_system", "") or "auto",
        diagnosis_code=getattr(item, "diagnosis_code", "") or "",
        frame_label=getattr(item, "frame_label", "") or "",
        mode_pindai=getattr(item, "mode_pindai", "") or "anatomi_lesi",
        structures=structures,
        segmented=int(bool(getattr(item, "segmented", 0)) or ai_parsers.is_segmented(anomalies, structures)),
        created_at=item.created_at,
    )


@router.get("", response_model=List[schemas.ScanHistoryOut])
def list_history(
    patient_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.ScanHistory)
    if patient_id:
        query = query.filter(models.ScanHistory.patient_id == patient_id)
    items = query.order_by(models.ScanHistory.created_at.desc()).all()
    return [_to_out(i) for i in items]


@router.get("/{history_id}", response_model=schemas.ScanHistoryOut)
def get_history(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = db.query(models.ScanHistory).filter(models.ScanHistory.id == history_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="History not found.")
    return _to_out(item)


@router.put("/{history_id}", response_model=schemas.ScanHistoryOut)
def update_history(
    history_id: int,
    payload: schemas.HistoryUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = db.query(models.ScanHistory).filter(models.ScanHistory.id == history_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="History not found.")

    update_data = payload.model_dump(exclude_unset=True)
    if "patient_id" in update_data and update_data["patient_id"] is not None:
        patient = db.query(models.Patient).filter(models.Patient.id == update_data["patient_id"]).first()
        if not patient:
            raise HTTPException(status_code=400, detail="Target patient not found.")

    if "anomalies" in update_data:
        item.anomalies_json = json.dumps(update_data.pop("anomalies") or [])

    for key, value in update_data.items():
        setattr(item, key, value)

    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.delete("/{history_id}", status_code=204)
def delete_history(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = db.query(models.ScanHistory).filter(models.ScanHistory.id == history_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="History not found.")

    # Hapus berkas fisik terkait (citra asli & preview) agar tidak menumpuk di disk
    for fname in {item.stored_filename, item.preview_filename}:
        if fname:
            fpath = os.path.join(settings.UPLOAD_DIR, fname)
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except OSError:
                    pass

    db.delete(item)
    db.commit()
    return None


@router.get("/{history_id}/image")
def get_history_image(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Menyajikan citra yang dapat ditampilkan di browser (hasil konversi jika berkas asli DICOM)."""
    item = db.query(models.ScanHistory).filter(models.ScanHistory.id == history_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="History not found.")

    fname = item.preview_filename or item.stored_filename
    fpath = os.path.join(settings.UPLOAD_DIR, fname)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Image file not found on the server.")

    return FileResponse(fpath)
