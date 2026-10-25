import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import models
from config import settings
from database import engine, SessionLocal, Base
from security import hash_password
from routers import auth, patients, history, scan, dashboard, clinical_history, app_config
from routers import clinical_profile, insight

# Membuat seluruh tabel database jika belum ada
Base.metadata.create_all(bind=engine)


def ensure_new_columns():
    """
    Migrasi ringan untuk SQLite: menambahkan kolom baru pada tabel scan_history
    jika database lama sudah ada.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "scan_history" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("scan_history")}
    with engine.connect() as conn:
        new_v3_cols = {
            "jenis_pemeriksaan": "VARCHAR(30) DEFAULT ''",
            "anatomical_area": "VARCHAR(80) DEFAULT ''",
            "tujuan_analisis": "VARCHAR(50) DEFAULT 'otomatis'",
            "diagnosis_code_system": "VARCHAR(20) DEFAULT 'auto'",
            "diagnosis_code": "VARCHAR(255) DEFAULT ''",
            "frame_label": "VARCHAR(120) DEFAULT ''",
            "structures_json": "TEXT DEFAULT '[]'",
            "mode_pindai": "VARCHAR(20) DEFAULT 'anatomi_lesi'",
            "segmented": "INTEGER DEFAULT 0",
        }
        for col, coltype in new_v3_cols.items():
            if col not in existing_cols:
                conn.execute(text(f"ALTER TABLE scan_history ADD COLUMN {col} {coltype}"))
        conn.commit()


ensure_new_columns()


def seed_admin_user():
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(
            models.User.username == settings.ADMIN_USERNAME
        ).first()
        if not existing:
            admin = models.User(
                username=settings.ADMIN_USERNAME,
                hashed_password=hash_password(settings.ADMIN_PASSWORD),
                full_name=settings.ADMIN_FULLNAME,
                role="admin",
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()


seed_admin_user()

app = FastAPI(
    title="Sistem Radiologi AI - Backend v2",
    description=(
        "Backend FastAPI untuk manajemen pasien, riwayat pemindaian, "
        "dan analisis citra medis (termasuk DICOM) berbasis AI."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Menyajikan berkas citra yang diunggah/dikonversi (preview DICOM, dsb.)
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(history.router)
app.include_router(scan.router)
app.include_router(dashboard.router)
app.include_router(clinical_history.router)
app.include_router(app_config.router)
app.include_router(clinical_profile.router)
app.include_router(clinical_profile.codes_router)
app.include_router(insight.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "radiology-backend-v2"}


# Menyajikan frontend statis (dashboard, pasien, riwayat, pemindaian) dari folder ../frontend.
# PENTING: mount ini harus didaftarkan PALING TERAKHIR, setelah semua route /api/*,
# karena StaticFiles di-mount pada path root "/" dan akan mencegat request yang
# cocok lebih dulu berdasarkan urutan pendaftaran route.
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
