from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), default="")
    role = Column(String(20), default="dokter")
    created_at = Column(DateTime, default=datetime.utcnow)


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    mrn = Column(String(50), unique=True, index=True, nullable=False)  # No. Rekam Medis
    name = Column(String(150), nullable=False)
    gender = Column(String(10), default="")  # L / P
    birth_date = Column(String(20), default="")
    phone = Column(String(30), default="")
    address = Column(Text, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    history = relationship("ScanHistory", back_populates="patient", cascade="all, delete-orphan")


class ScanHistory(Base):
    __tablename__ = "scan_history"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=True)

    original_filename = Column(String(255), default="")
    stored_filename = Column(String(255), default="")   # berkas asli (bisa .dcm)
    preview_filename = Column(String(255), default="")  # versi PNG/JPEG yang bisa ditampilkan
    is_dicom = Column(Integer, default=0)

    model_used = Column(String(100), default="")
    diagnosis = Column(String(255), default="")
    confidence = Column(Float, default=0.0)
    summary = Column(Text, default="")
    anomalies_json = Column(Text, default="[]")  # daftar kelainan tersimpan sebagai teks JSON

    status = Column(String(20), default="success")  # success / error
    error_message = Column(Text, default="")

    # --- Metadata pemindaian tambahan (v3) ---
    jenis_pemeriksaan = Column(String(30), default="")  # X-Ray / CT-Scan / MRI / USG / PET scan
    anatomical_area = Column(String(80), default="")
    tujuan_analisis = Column(String(50), default="otomatis")
    diagnosis_code_system = Column(String(20), default="auto")  # auto/icd10/icd11/snomed/sdki/nanda
    diagnosis_code = Column(String(255), default="")  # kode terpilih, mis. "ICD-10 I25.82"
    frame_label = Column(String(120), default="")  # nama/label frame citra pada sesi multi-gambar
    mode_pindai = Column(String(20), default="anatomi_lesi")  # anatomi / lesi / anatomi_lesi
    structures_json = Column(Text, default="[]")  # struktur anatomi toraks (box + polygon) hasil deteksi/segmentasi model AI
    segmented = Column(Integer, default=0)  # 0 = baru deteksi objek (panggilan 1), 1 = segmentasi (panggilan 2) sudah dijalankan

    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="history")


class ClinicalHistory(Base):
    """Riwayat klinis pasien (Clinical History) - digunakan sebagai konteks tambahan saat pemindaian AI."""
    __tablename__ = "clinical_history"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), unique=True, nullable=False)

    identitas_pasien = Column(Text, default="")
    keluhan_utama = Column(Text, default="")
    pemeriksaan_fisik = Column(Text, default="")
    pemeriksaan_penunjang = Column(Text, default="")
    riwayat_medis = Column(Text, default="")
    keterangan_lainnya = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient")


class ClinicalProfile(Base):
    """Profil klinis terstruktur per pasien: diagnosis + kode, matriks impact, skor agregat,
    bahaya klinis, dan kapasitas organ. Isi disimpan sebagai JSON teks."""
    __tablename__ = "clinical_profile"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), unique=True, nullable=False)
    data_json = Column(Text, default="{}")
    code_system = Column(String(20), default="icd10")  # sistem kode yang ditampilkan terakhir
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient")


