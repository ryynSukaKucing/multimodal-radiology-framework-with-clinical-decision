import json
from collections import Counter
from datetime import datetime, timedelta

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

import models
import schemas
from database import get_db
from routers.history import _to_out
from security import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=schemas.DashboardStats)
def get_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    total_patients = db.query(func.count(models.Patient.id)).scalar() or 0
    total_scans = db.query(func.count(models.ScanHistory.id)).scalar() or 0

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    scans_today = db.query(func.count(models.ScanHistory.id)).filter(
        models.ScanHistory.created_at >= today_start
    ).scalar() or 0

    scans_this_week = db.query(func.count(models.ScanHistory.id)).filter(
        models.ScanHistory.created_at >= week_start
    ).scalar() or 0

    success_count = db.query(func.count(models.ScanHistory.id)).filter(
        models.ScanHistory.status == "success"
    ).scalar() or 0
    success_rate = round((success_count / total_scans) * 100, 1) if total_scans else 0.0

    # Distribusi tingkat keparahan (severity) dari seluruh anomali yang tercatat
    severity_counter = Counter()
    all_items = db.query(models.ScanHistory).filter(models.ScanHistory.status == "success").all()
    for item in all_items:
        try:
            anomalies = json.loads(item.anomalies_json or "[]")
        except json.JSONDecodeError:
            anomalies = []
        if not anomalies:
            severity_counter["No abnormality"] += 1
        for a in anomalies:
            sev = (a.get("severity") or "Unknown").strip()
            severity_counter[sev] += 1

    # Tren pemindaian 7 hari terakhir
    scans_per_day = []
    for i in range(6, -1, -1):
        day = (today_start - timedelta(days=i))
        next_day = day + timedelta(days=1)
        count = db.query(func.count(models.ScanHistory.id)).filter(
            models.ScanHistory.created_at >= day,
            models.ScanHistory.created_at < next_day,
        ).scalar() or 0
        scans_per_day.append({"date": day.strftime("%Y-%m-%d"), "count": count})

    recent = db.query(models.ScanHistory).order_by(
        models.ScanHistory.created_at.desc()
    ).limit(8).all()

    return schemas.DashboardStats(
        total_patients=total_patients,
        total_scans=total_scans,
        scans_this_week=scans_this_week,
        scans_today=scans_today,
        success_rate=success_rate,
        severity_breakdown=dict(severity_counter),
        scans_per_day=scans_per_day,
        recent_history=[_to_out(i) for i in recent],
    )


@router.get("/day")
def scans_by_day(
    date: Optional[str] = None,
    tz_offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Scans for ONE day, bucketed per hour. `date` is YYYY-MM-DD in the viewer's local time;
    `tz_offset` is the viewer's UTC offset in minutes (e.g. 420 for Jakarta)."""
    offset = timedelta(minutes=max(-840, min(840, tz_offset)))
    if date:
        try:
            day_local = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date. Use YYYY-MM-DD.")
    else:
        day_local = (datetime.utcnow() + offset).replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = day_local - offset
    end_utc = start_utc + timedelta(days=1)
    rows = db.query(models.ScanHistory.created_at).filter(
        models.ScanHistory.created_at >= start_utc,
        models.ScanHistory.created_at < end_utc,
    ).all()
    hours = [0] * 24
    for (created,) in rows:
        hours[(created + offset).hour] += 1
    return {"date": day_local.strftime("%Y-%m-%d"), "total": sum(hours), "hours": hours}
