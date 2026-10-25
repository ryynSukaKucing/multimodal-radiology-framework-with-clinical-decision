from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

import models
import schemas
from database import get_db
from security import get_current_user

router = APIRouter(prefix="/api/patients", tags=["Database Pasien"])


@router.get("", response_model=List[schemas.PatientOut])
def list_patients(
    q: Optional[str] = Query(None, description="Cari berdasarkan nama atau No. RM"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Patient)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(models.Patient.name.ilike(like), models.Patient.mrn.ilike(like)))

    patients = query.order_by(models.Patient.created_at.desc()).all()

    result = []
    for p in patients:
        total_scans = db.query(func.count(models.ScanHistory.id)).filter(
            models.ScanHistory.patient_id == p.id
        ).scalar()
        item = schemas.PatientOut.model_validate(p)
        item.total_scans = total_scans or 0
        result.append(item)
    return result


@router.post("", response_model=schemas.PatientOut, status_code=201)
def create_patient(
    payload: schemas.PatientCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    existing = db.query(models.Patient).filter(models.Patient.mrn == payload.mrn).first()
    if existing:
        raise HTTPException(status_code=400, detail="Medical Record No. (MRN) is already registered.")

    patient = models.Patient(**payload.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)

    out = schemas.PatientOut.model_validate(patient)
    out.total_scans = 0
    return out


@router.get("/{patient_id}", response_model=schemas.PatientOut)
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record not found.")

    total_scans = db.query(func.count(models.ScanHistory.id)).filter(
        models.ScanHistory.patient_id == patient.id
    ).scalar()
    out = schemas.PatientOut.model_validate(patient)
    out.total_scans = total_scans or 0
    return out


@router.put("/{patient_id}", response_model=schemas.PatientOut)
def update_patient(
    patient_id: int,
    payload: schemas.PatientUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record not found.")

    update_data = payload.model_dump(exclude_unset=True)

    if "mrn" in update_data and update_data["mrn"] != patient.mrn:
        dup = db.query(models.Patient).filter(models.Patient.mrn == update_data["mrn"]).first()
        if dup:
            raise HTTPException(status_code=400, detail="Medical Record No. (MRN) is already used by another patient.")

    for key, value in update_data.items():
        setattr(patient, key, value)

    db.commit()
    db.refresh(patient)

    total_scans = db.query(func.count(models.ScanHistory.id)).filter(
        models.ScanHistory.patient_id == patient.id
    ).scalar()
    out = schemas.PatientOut.model_validate(patient)
    out.total_scans = total_scans or 0
    return out


@router.delete("/{patient_id}", status_code=204)
def delete_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record not found.")

    db.delete(patient)  # cascade akan menghapus riwayat pemindaian terkait
    db.commit()
    return None
