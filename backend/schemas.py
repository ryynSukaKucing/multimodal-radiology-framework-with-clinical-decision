from datetime import datetime
from typing import Optional, List, Any

from pydantic import BaseModel, ConfigDict


# ---------- Auth ----------

class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    full_name: str
    role: str


# ---------- Patient ----------

class PatientBase(BaseModel):
    mrn: str
    name: str
    gender: Optional[str] = ""
    birth_date: Optional[str] = ""
    phone: Optional[str] = ""
    address: Optional[str] = ""
    notes: Optional[str] = ""


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    mrn: Optional[str] = None
    name: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class PatientOut(PatientBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    total_scans: int = 0


# ---------- Scan History ----------

class ScanHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    original_filename: str
    preview_filename: str
    is_dicom: int
    model_used: str
    diagnosis: str
    confidence: float
    summary: str
    anomalies: List[Any] = []
    status: str
    error_message: str = ""
    jenis_pemeriksaan: str = ""
    anatomical_area: str = ""
    tujuan_analisis: str = "otomatis"
    diagnosis_code_system: str = "auto"
    diagnosis_code: str = ""
    frame_label: str = ""
    mode_pindai: str = "anatomi_lesi"
    structures: List[Any] = []   # struktur anatomi toraks (deteksi + segmentasi) dari model AI
    segmented: int = 0           # 0 = hanya deteksi objek, 1 = segmentasi sudah dijalankan
    created_at: datetime


class HistoryUpdate(BaseModel):
    patient_id: Optional[int] = None
    diagnosis: Optional[str] = None
    summary: Optional[str] = None
    diagnosis_code: Optional[str] = None
    diagnosis_code_system: Optional[str] = None
    anomalies: Optional[List[Any]] = None


# ---------- Clinical History ----------

class ClinicalHistoryUpdate(BaseModel):
    identitas_pasien: Optional[str] = None
    keluhan_utama: Optional[str] = None
    pemeriksaan_fisik: Optional[str] = None
    pemeriksaan_penunjang: Optional[str] = None
    riwayat_medis: Optional[str] = None
    keterangan_lainnya: Optional[str] = None


class ClinicalHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: int
    identitas_pasien: str = ""
    keluhan_utama: str = ""
    pemeriksaan_fisik: str = ""
    pemeriksaan_penunjang: str = ""
    riwayat_medis: str = ""
    keterangan_lainnya: str = ""
    updated_at: Optional[datetime] = None


# ---------- Dashboard ----------

class DashboardStats(BaseModel):
    total_patients: int
    total_scans: int
    scans_this_week: int
    scans_today: int
    success_rate: float
    severity_breakdown: dict
    scans_per_day: List[dict]
    recent_history: List[ScanHistoryOut]


# ---------- Profil Klinis terstruktur ----------

class ClinicalProfileUpdate(BaseModel):
    data: dict
    code_system: Optional[str] = None


class ClinicalProfileOut(BaseModel):
    patient_id: int
    data: dict = {}
    code_system: str = "icd10"
    updated_at: Optional[datetime] = None


class AiRequestBase(BaseModel):
    model: str = "kr/claude-sonnet-4.5"
    authorization: Optional[str] = None


class ProfileAiGenerate(AiRequestBase):
    code_system: str = "icd10"
    merge: bool = False  # True: tambahkan ke profil yang ada, False: ganti


class ProfileAiCodes(AiRequestBase):
    code_system: str = "icd10"
    diagnosis_ids: Optional[List[str]] = None  # None = semua diagnosis yang belum punya kode untuk sistem tsb


# ---------- Insight temuan (peta opsi hasil pemindaian) ----------

class InsightRequest(AiRequestBase):
    branch: str
    patient_id: Optional[int] = None
    history_id: Optional[int] = None
    anomaly_index: Optional[int] = None  # posisi temuan pada daftar anomalies riwayat (untuk menyimpan hasil)
    finding: dict  # label, severity, description, box
    diagnosis: str = ""
    summary: str = ""
    jenis_pemeriksaan: str = ""
    anatomical_area: str = ""
