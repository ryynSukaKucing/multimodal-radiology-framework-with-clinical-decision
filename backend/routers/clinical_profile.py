import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import code_systems
import llm_client
import models
import schemas
from database import get_db
from security import get_current_user

router = APIRouter(prefix="/api/clinical-profile", tags=["Profil Klinis"])
codes_router = APIRouter(prefix="/api/code-systems", tags=["Kode Diagnosis"])

# ---- Metadata yang dipakai bersama frontend dan prompt AI ----

# (key, label, bobot, keluarga) keluarga yang sama hanya dihitung sekali (bobot tertinggi).
CCI_CATEGORIES = [
    ("none", "Tidak termasuk indeks Charlson", 0, ""),
    ("mi", "Infark miokard", 1, ""),
    ("chf", "Gagal jantung kongestif", 1, ""),
    ("pvd", "Penyakit vaskular perifer", 1, ""),
    ("cvd", "Penyakit serebrovaskular", 1, ""),
    ("dementia", "Demensia", 1, ""),
    ("copd", "Penyakit paru kronik", 1, ""),
    ("ctd", "Penyakit jaringan ikat", 1, ""),
    ("pud", "Penyakit ulkus peptikum", 1, ""),
    ("liver_mild", "Penyakit hati ringan", 1, "liver"),
    ("dm", "Diabetes tanpa kerusakan organ target", 1, "dm"),
    ("dm_end", "Diabetes dengan kerusakan organ target", 2, "dm"),
    ("hemiplegia", "Hemiplegia atau paraplegia", 2, ""),
    ("renal", "Penyakit ginjal sedang atau berat", 2, ""),
    ("tumor", "Tumor padat atau keganasan tanpa metastasis", 2, "tumor"),
    ("leukemia", "Leukemia", 2, ""),
    ("lymphoma", "Limfoma", 2, ""),
    ("liver_severe", "Penyakit hati sedang atau berat", 3, "liver"),
    ("mets", "Tumor padat metastasis", 6, "tumor"),
    ("aids", "AIDS", 6, ""),
]
CCI_WEIGHT = {k: w for k, _l, w, _f in CCI_CATEGORIES}
CCI_FAMILY = {k: f for k, _l, _w, f in CCI_CATEGORIES}

KELOMPOK = ["Onkologi", "Endokrin", "Renal", "Kardiovaskular", "Neurologi", "Respirasi", "Muskuloskeletal",
            "Infeksi", "Hematologi", "Gastrointestinal", "Lainnya"]
DAMPAK_LEVELS = ["primary", "critical", "high", "moderate", "low"]
TONES = ["merah", "kuning", "hijau", "biru"]
ORGAN_KEYS = ["ecog", "egfr", "gds", "lvef", "sgot", "sgpt", "hb"]
HAZARD_LEVELS = ["Kritis", "Tinggi", "Sedang", "Rendah"]


def cci_label(score: int) -> str:
    if score >= 5:
        return "Risiko Tinggi"
    if score >= 3:
        return "Risiko Sedang"
    if score >= 1:
        return "Risiko Ringan"
    return "Risiko Rendah"


def compute_cci(diagnoses: List[dict]) -> int:
    fam_best: Dict[str, int] = {}
    total = 0
    for d in diagnoses:
        key = d.get("cci_kategori") or "none"
        w = CCI_WEIGHT.get(key, 0)
        fam = CCI_FAMILY.get(key, "")
        if not w:
            continue
        if fam:
            fam_best[fam] = max(fam_best.get(fam, 0), w)
        else:
            total += w
    return total + sum(fam_best.values())


def _num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ".").strip().rstrip("%"))
    except ValueError:
        return None


def _clean_str(v, limit=300) -> str:
    return str(v).strip()[:limit] if v is not None else ""


def _clean_list(v, max_items=8, limit=80) -> List[str]:
    if isinstance(v, str):
        v = [x for x in v.replace(";", ",").split(",")]
    if not isinstance(v, list):
        return []
    out = []
    for x in v:
        t = _clean_str(x, limit)
        if t and t.lower() not in [o.lower() for o in out]:
            out.append(t)
    return out[:max_items]


def _normalize_kode_entry(system: str, entry: Any) -> Optional[dict]:
    if entry is None:
        return None
    if isinstance(entry, str):
        entry = {"kode": entry}
    if not isinstance(entry, dict):
        return None
    kode = code_systems.normalize_code(system, entry.get("kode") or entry.get("code"))
    if not kode:
        return None
    check = code_systems.validate_format(system, kode)
    local_names = {c["code"]: c["name"] for c in code_systems.search_local(system, "", limit=500)}
    return {
        "kode": kode,
        "nama": _clean_str(entry.get("nama") or entry.get("name") or local_names.get(kode, ""), 200),
        "sumber": _clean_str(entry.get("sumber") or "manual", 20),
        "format_valid": check["valid"],
        "ada_di_daftar_lokal": kode in local_names,
    }


def normalize_diagnosis(d: dict) -> dict:
    kodes_in = d.get("kodes") if isinstance(d.get("kodes"), dict) else {}
    kodes = {}
    for sys_key, entry in kodes_in.items():
        if sys_key in code_systems.SYSTEM_KEYS:
            e = _normalize_kode_entry(sys_key, entry)
            if e:
                kodes[sys_key] = e
    tautan = d.get("tautan") if isinstance(d.get("tautan"), dict) else {}
    cci = d.get("cci_kategori") if d.get("cci_kategori") in CCI_WEIGHT else "none"
    dampak = d.get("dampak") if d.get("dampak") in DAMPAK_LEVELS else "moderate"
    peran = "utama" if d.get("peran") == "utama" else "komorbid"
    return {
        "id": _clean_str(d.get("id"), 40) or f"d{uuid.uuid4().hex[:8]}",
        "nama": _clean_str(d.get("nama"), 200),
        "peran": peran,
        "kelompok": d.get("kelompok") if d.get("kelompok") in KELOMPOK else "Lainnya",
        "onset": _clean_str(d.get("onset"), 60),
        "severity": _clean_str(d.get("severity"), 120),
        "trajektori": _clean_str(d.get("trajektori"), 120),
        "dampak": dampak,
        "dampak_ket": _clean_str(d.get("dampak_ket"), 120),
        "status_kontrol": _clean_str(d.get("status_kontrol"), 120),
        "aksi_medis": _clean_str(d.get("aksi_medis"), 80),
        "catatan_kartu": _clean_str(d.get("catatan_kartu"), 80),
        "catatan_klinis": _clean_str(d.get("catatan_klinis"), 400),
        "obat": _clean_list(d.get("obat"), 8, 80),
        "catatan_tone": d.get("catatan_tone") if d.get("catatan_tone") in TONES else "biru",
        "tautan": {
            "teks": _clean_str(tautan.get("teks"), 60),
            "target": tautan.get("target") if tautan.get("target") in ("scan", "lab", "edit") else "edit",
        },
        "cci_kategori": cci,
        "kodes": kodes,
    }


def normalize_profile(data: Any) -> Dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    diagnoses = [normalize_diagnosis(d) for d in (data.get("diagnoses") or []) if isinstance(d, dict) and _clean_str(d.get("nama"))]
    # tepat satu diagnosis utama: bila tidak ada, jadikan yang pertama; bila lebih dari satu, sisanya komorbid
    utama_seen = False
    for d in diagnoses:
        if d["peran"] == "utama":
            if utama_seen:
                d["peran"] = "komorbid"
            utama_seen = True
    if diagnoses and not utama_seen:
        diagnoses[0]["peran"] = "utama"

    skor_in = data.get("skor") if isinstance(data.get("skor"), dict) else {}
    cci_manual = bool(skor_in.get("cci_manual"))
    cci_val = _num(skor_in.get("cci_nilai")) if cci_manual else None
    cci_nilai = int(cci_val) if cci_val is not None else compute_cci(diagnoses)
    pb, pt = _num(skor_in.get("pemulihan_baseline")), _num(skor_in.get("pemulihan_terkoreksi"))
    skor = {
        "cci_nilai": cci_nilai,
        "cci_manual": cci_manual,
        "cci_label": cci_label(cci_nilai),
        "pemulihan_baseline": max(0, min(100, pb)) if pb is not None else None,
        "pemulihan_terkoreksi": max(0, min(100, pt)) if pt is not None else None,
        "timeline_terkoreksi": _clean_str(skor_in.get("timeline_terkoreksi"), 80),
        "catatan": _clean_str(skor_in.get("catatan"), 400),
    }

    hazards = []
    for h in data.get("hazards") or []:
        if not isinstance(h, dict) or not _clean_str(h.get("judul")):
            continue
        ov = h.get("override") if isinstance(h.get("override"), dict) else None
        hazards.append({
            "id": _clean_str(h.get("id"), 40) or f"h{uuid.uuid4().hex[:8]}",
            "judul": _clean_str(h.get("judul"), 160),
            "tingkat": h.get("tingkat") if h.get("tingkat") in HAZARD_LEVELS else "Sedang",
            "deskripsi": _clean_str(h.get("deskripsi"), 700),
            "aksi": [_clean_str(a, 80) for a in (h.get("aksi") or []) if _clean_str(a)][:4],
            "sumber": _clean_str(h.get("sumber"), 120),
            "override": {"alasan": _clean_str(ov.get("alasan"), 300), "waktu": _clean_str(ov.get("waktu"), 40)} if ov else None,
        })

    organ_in = data.get("organ") if isinstance(data.get("organ"), dict) else {}
    organ: Dict[str, Any] = {k: _num(organ_in.get(k)) for k in ORGAN_KEYS}
    ket_in = organ_in.get("keterangan") if isinstance(organ_in.get("keterangan"), dict) else {}
    organ["keterangan"] = {k: _clean_str(ket_in.get(k), 160) for k in ORGAN_KEYS if _clean_str(ket_in.get(k))}

    return {"diagnoses": diagnoses, "skor": skor, "hazards": hazards, "organ": organ}


def _empty_profile() -> Dict[str, Any]:
    return normalize_profile({})


def _get_patient(db: Session, patient_id: int) -> models.Patient:
    p = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return p


def _get_row(db: Session, patient_id: int) -> Optional[models.ClinicalProfile]:
    return db.query(models.ClinicalProfile).filter(models.ClinicalProfile.patient_id == patient_id).first()


def _save(db: Session, patient_id: int, data: Dict[str, Any], code_system: Optional[str] = None) -> models.ClinicalProfile:
    row = _get_row(db, patient_id)
    if not row:
        row = models.ClinicalProfile(patient_id=patient_id)
        db.add(row)
    row.data_json = json.dumps(data, ensure_ascii=False)
    if code_system:
        row.code_system = code_systems.normalize_system(code_system)
    db.commit()
    db.refresh(row)
    return row


def _out(patient_id: int, row: Optional[models.ClinicalProfile]) -> schemas.ClinicalProfileOut:
    if not row:
        return schemas.ClinicalProfileOut(patient_id=patient_id, data=_empty_profile())
    try:
        data = json.loads(row.data_json or "{}")
    except json.JSONDecodeError:
        data = {}
    return schemas.ClinicalProfileOut(
        patient_id=patient_id, data=normalize_profile(data), code_system=row.code_system or "icd10", updated_at=row.updated_at,
    )


# ---------------------------------------------------------------- endpoint metadata & kode

@router.get("/meta")
def profile_meta(current_user: models.User = Depends(get_current_user)):
    return {
        "code_systems": code_systems.SYSTEMS,
        "cci_categories": [{"key": k, "label": l, "weight": w, "family": f} for k, l, w, f in CCI_CATEGORIES],
        "kelompok": KELOMPOK,
        "dampak_levels": DAMPAK_LEVELS,
        "hazard_levels": HAZARD_LEVELS,
    }


@codes_router.get("")
def list_code_systems(current_user: models.User = Depends(get_current_user)):
    return code_systems.SYSTEMS


@codes_router.get("/search")
def search_codes(
    system: str = Query("icd10"),
    q: str = Query(""),
    current_user: models.User = Depends(get_current_user),
):
    sysk = code_systems.normalize_system(system)
    return {"system": sysk, "results": code_systems.search_local(sysk, q), "note": "Daftar lokal ringkas. Verifikasi pada rilis resmi."}


@codes_router.get("/validate")
def validate_code(
    system: str = Query("icd10"),
    code: str = Query(""),
    current_user: models.User = Depends(get_current_user),
):
    sysk = code_systems.normalize_system(system)
    res = code_systems.validate_format(sysk, code)
    res["normalized"] = code_systems.normalize_code(sysk, code)
    return res


# ---------------------------------------------------------------- CRUD profil

@router.get("/{patient_id}", response_model=schemas.ClinicalProfileOut)
def get_profile(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_patient(db, patient_id)
    return _out(patient_id, _get_row(db, patient_id))


@router.put("/{patient_id}", response_model=schemas.ClinicalProfileOut)
def update_profile(
    patient_id: int,
    payload: schemas.ClinicalProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_patient(db, patient_id)
    row = _save(db, patient_id, normalize_profile(payload.data), payload.code_system)
    return _out(patient_id, row)


# ---------------------------------------------------------------- AI

def _profile_prompt(context: str, code_system: str, existing: Optional[dict]) -> str:
    cci_keys = ", ".join(f'"{k}" ({l})' for k, l, _w, _f in CCI_CATEGORIES)
    sys_label = code_systems.SYSTEM_LABEL.get(code_system, code_system)
    sys_hint = next((s["hint"] for s in code_systems.SYSTEMS if s["key"] == code_system), "")
    existing_txt = ""
    if existing and existing.get("diagnoses"):
        existing_txt = "\nPROFIL YANG SUDAH ADA (pertahankan dan lengkapi, jangan duplikasi):\n" + json.dumps(existing, ensure_ascii=False)[:5000] + "\n"
    return (
        "Anda adalah asisten rekam medis dan dukungan keputusan klinis. Susun PROFIL KLINIS TERSTRUKTUR pasien dari konteks berikut. "
        + llm_client.DISCLAIMER_RULES + "\n\n"
        + context[:14000] + "\n" + existing_txt + "\n"
        + "Write ALL free-text values in ENGLISH; keep the JSON keys and enumerated values exactly as specified. "
        + "Balas HANYA dengan satu objek JSON tanpa markdown dengan bentuk:\n"
        + "{\n"
        + '  "diagnoses": [ {"nama": "...", "peran": "utama atau komorbid", "kelompok": "salah satu dari: ' + ", ".join(KELOMPOK) + '",\n'
        + '     "onset": "e.g. Acute / Malignant, Acute, Chronic", "severity": "mis. Stage III (High Grade), Uncontrolled, Moderate Impairment",\n'
        + '     "trajektori": "mis. Curative Intent, Chronic Management, Support / Monitoring",\n'
        + '     "dampak": "primary (hanya diagnosis utama), critical, high, moderate, atau low = dampak terhadap diagnosis utama", "dampak_ket": "alasan singkat dampak",\n'
        + '     "status_kontrol": "mis. Terkontrol Obat, Terganggu, Progresif (Active)", "aksi_medis": "satu aksi singkat, mis. Koreksi Dosis",\n'
        + '     "catatan_kartu": "satu frasa penanda risiko, mis. Resiko Infeksi Luka", "catatan_tone": "merah, kuning, hijau, atau biru",\n'
        + '     "catatan_klinis": "1-2 kalimat rinci: lokasi/ukuran/hasil pemeriksaan pendukung dan implikasi untuk perawatan, hanya dari data pasien",\n'
        + '     "obat": ["obat/regimen yang sedang atau direncanakan untuk kondisi ini, hanya yang tertulis di data; kosongkan bila tidak ada"],\n'
        + '     "tautan": {"teks": "mis. Cek Fungsi Ginjal", "target": "scan (lihat citra), lab (data laboratorium), atau edit"},\n'
        + '     "cci_kategori": "satu kunci dari: ' + cci_keys + '",\n'
        + f'     "kode": {{"kode": "kode {sys_label} yang paling sesuai ({sys_hint}), kosongkan bila ragu", "nama": "nama resmi kode"}} }}\n'
        + "  ],\n"
        + '  "skor": {"pemulihan_baseline": "angka 0-100 atau null", "pemulihan_terkoreksi": "angka 0-100 atau null", "timeline_terkoreksi": "mis. 10 - 14 Bulan atau kosong", "catatan": "asumsi estimasi"},\n'
        + '  "hazards": [ {"judul": "...", "tingkat": "Kritis, Tinggi, Sedang, atau Rendah", "deskripsi": "interaksi atau bahaya klinis antar kondisi pasien", "aksi": ["maks 3 tindakan singkat"]} ],\n'
        + '  "organ": {"ecog": "0-4 atau null", "egfr": "mL/min atau null", "gds": "mg/dL atau null", "lvef": "% atau null", "sgot": "U/L atau null", "sgpt": "U/L atau null", "hb": "g/dL atau null",\n'
        + '     "keterangan": {"ecog": "arti klinis singkat", "egfr": "...", "gds": "...", "lvef": "...", "sgot": "...", "hb": "..."} }\n'
        + "}\n"
        + "Aturan khusus: (1) tepat satu diagnosis dengan peran utama. (2) Nilai organ HANYA dari angka yang tertulis di konteks, selain itu null. "
        + "(3) Estimasi kesembuhan dan timeline hanya bila dapat dipertanggungjawabkan dari data, selain itu null atau kosong. "
        + "(4) Kode diagnosis harus kode baku yang Anda yakini; bila tidak yakin, kosongkan. (5) hazards hanya untuk interaksi yang masuk akal secara klinis dari data pasien. "
        + "(6) Tingkat detail: severity memuat parameter terukur bila ada (mis. 'Uncontrolled (GDS > 200 mg/dL)', 'Stage 3 (eGFR 45 mL/min)'); "
        + "deskripsi hazard 2 kalimat yang menyebut kondisi pemicu, nilai data yang relevan, dan konsekuensi klinisnya (mis. batasan media kontras atau regimen obat pada CKD, risiko infeksi luka pada DM tak terkontrol, kontraindikasi NSAID pada gangguan ginjal) dengan 1-3 aksi konkret; "
        + "urutkan hazards dari Kritis ke Rendah; isi keterangan organ untuk setiap nilai yang ada; catatan skor menyebut asumsi estimasi kesembuhan. "
        + "Jangan mengarang angka, obat, atau temuan yang tidak ada di data."
    )


def _from_ai_diagnosis(raw: dict, code_system: str) -> dict:
    d = dict(raw)
    kode = raw.get("kode")
    if kode:
        d["kodes"] = {code_system: {**(kode if isinstance(kode, dict) else {"kode": kode}), "sumber": "ai"}}
    return d


@router.post("/{patient_id}/ai-generate", response_model=schemas.ClinicalProfileOut)
async def ai_generate_profile(
    patient_id: int,
    req: schemas.ProfileAiGenerate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_patient(db, patient_id)
    code_system = code_systems.normalize_system(req.code_system)
    context = llm_client.build_patient_context(db, patient_id, include_scans=True, include_profile=False)
    has_data = bool(llm_client.clinical_text(db, patient_id) or llm_client.latest_scans_text(db, patient_id))
    if not has_data:
        raise HTTPException(status_code=400, detail="There is no Clinical History or scan result for this patient yet. Enter or upload clinical data first.")

    row = _get_row(db, patient_id)
    existing = _out(patient_id, row).data if (row and req.merge) else None
    raw = await llm_client.chat_json(_profile_prompt(context, code_system, existing), req.model, req.authorization, max_tokens=4500)
    raw = llm_client.scrub(raw)
    if not isinstance(raw, dict):
        raise HTTPException(status_code=502, detail="The AI response is not a valid profile object.")

    new_data: Dict[str, Any] = {
        "diagnoses": [_from_ai_diagnosis(d, code_system) for d in (raw.get("diagnoses") or []) if isinstance(d, dict)],
        "skor": raw.get("skor") if isinstance(raw.get("skor"), dict) else {},
        "hazards": raw.get("hazards") if isinstance(raw.get("hazards"), list) else [],
        "organ": raw.get("organ") if isinstance(raw.get("organ"), dict) else {},
    }
    if existing:
        by_name = {d["nama"].lower(): d for d in existing["diagnoses"]}
        merged = list(existing["diagnoses"])
        for d in new_data["diagnoses"]:
            nm = _clean_str(d.get("nama")).lower()
            if nm and nm not in by_name:
                merged.append(d)
        new_data["diagnoses"] = merged
        seen = {h["judul"].lower() for h in existing["hazards"]}
        new_data["hazards"] = existing["hazards"] + [h for h in new_data["hazards"] if isinstance(h, dict) and _clean_str(h.get("judul")).lower() not in seen]
        for k in ORGAN_KEYS:
            if new_data["organ"].get(k) in (None, "") and existing["organ"].get(k) is not None:
                new_data["organ"][k] = existing["organ"][k]
        ai_ket = new_data["organ"].get("keterangan") if isinstance(new_data["organ"].get("keterangan"), dict) else {}
        new_data["organ"]["keterangan"] = {**ai_ket, **existing["organ"].get("keterangan", {})}

    normalized = normalize_profile(new_data)
    if not normalized["diagnoses"]:
        raise HTTPException(status_code=502, detail="The AI found no diagnosis in the patient data. Complete the Clinical History and try again.")
    row = _save(db, patient_id, normalized, code_system)
    return _out(patient_id, row)


@router.post("/{patient_id}/ai-codes", response_model=schemas.ClinicalProfileOut)
async def ai_fill_codes(
    patient_id: int,
    req: schemas.ProfileAiCodes,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Mengisi kode diagnosis untuk sistem terpilih. AI mengusulkan kode, lalu format divalidasi dan dicocokkan ke daftar lokal."""
    _get_patient(db, patient_id)
    row = _get_row(db, patient_id)
    if not row:
        raise HTTPException(status_code=400, detail="The patient clinical profile does not exist yet.")
    data = _out(patient_id, row).data
    system = code_systems.normalize_system(req.code_system)
    if system == "lainnya":
        raise HTTPException(status_code=400, detail="The 'Other' system is filled in manually.")

    targets = [d for d in data["diagnoses"]
               if (d["id"] in req.diagnosis_ids if req.diagnosis_ids else system not in d["kodes"])]
    if not targets:
        return _out(patient_id, row)

    sys_label = code_systems.SYSTEM_LABEL[system]
    hint = next(s["hint"] for s in code_systems.SYSTEMS if s["key"] == system)
    lines = "\n".join(f'- id "{d["id"]}": {d["nama"]} ({d["severity"] or "-"})' for d in targets)
    prompt = (
        f"Tentukan kode {sys_label} yang paling sesuai untuk tiap diagnosis berikut. Format kode: {hint}. "
        "Bila Anda tidak yakin pada kode tertentu, kosongkan kode (jangan menebak). "
        + llm_client.DISCLAIMER_RULES + "\n\nDAFTAR DIAGNOSIS:\n" + lines + "\n\n"
        'Balas HANYA JSON: {"codes": [{"id": "...", "kode": "...", "nama": "nama resmi kode"}]}'
    )
    raw = llm_client.scrub(await llm_client.chat_json(prompt, req.model, req.authorization, max_tokens=1800))
    items = raw.get("codes") if isinstance(raw, dict) else raw
    ai_map = {str(i.get("id")): i for i in (items or []) if isinstance(i, dict)}

    for d in data["diagnoses"]:
        if d["id"] not in {t["id"] for t in targets}:
            continue
        it = ai_map.get(d["id"])
        if it and (it.get("kode") or "").strip():
            d["kodes"][system] = {"kode": it.get("kode"), "nama": it.get("nama", ""), "sumber": "ai"}
        else:
            match = code_systems.best_local_match(system, d["nama"])
            if match:
                d["kodes"][system] = {"kode": match["code"], "nama": match["name"], "sumber": "lokal"}
    row = _save(db, patient_id, normalize_profile(data), system)
    return _out(patient_id, row)
