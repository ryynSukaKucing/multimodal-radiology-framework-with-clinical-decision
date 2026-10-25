"""Sistem kode diagnosis (ICD-10/11, ICD-O-3, SNOMED CT, ICPC-2, NANDA-I, SDKI, dll).

Fungsi modul ini:
- daftar sistem kode untuk dropdown di frontend,
- validasi FORMAT kode (bukan validasi keberadaan kode di rilis resmi),
- pencarian ringkas pada daftar lokal berisi kode yang umum dipakai.

Penting: daftar lokal hanya rujukan cepat. Kode dari AI maupun daftar lokal tetap harus
diverifikasi klinisi/koder terhadap rilis resmi (WHO ICD, SNOMED International, PPNI, NANDA-I).
"""
import re
from typing import List, Optional

SYSTEMS = [
    {"key": "icd10", "label": "ICD-10", "group": "Klinis", "hint": "e.g. C40.2, E11.65, N18.3"},
    {"key": "icd11", "label": "ICD-11", "group": "Klinis", "hint": "e.g. 5A11, GB61, BA00"},
    {"key": "icdo3", "label": "ICD-O-3", "group": "Oncology", "hint": "topography C40.2 or morphology M9180/3"},
    {"key": "snomed", "label": "SNOMED CT", "group": "Klinis", "hint": "6 to 18 digits, e.g. 44054006"},
    {"key": "icpc2", "label": "ICPC-2", "group": "Primary care", "hint": "e.g. T90, K86"},
    {"key": "nanda", "label": "NANDA-I", "group": "Nursing", "hint": "5 digits, e.g. 00132"},
    {"key": "sdki", "label": "SDKI", "group": "Nursing", "hint": "e.g. D.0077"},
    {"key": "lainnya", "label": "Other (manual)", "group": "Other", "hint": "free-form code, e.g. an internal hospital code"},
]
SYSTEM_KEYS = [s["key"] for s in SYSTEMS]
SYSTEM_LABEL = {s["key"]: s["label"] for s in SYSTEMS}

_PATTERNS = {
    "icd10": re.compile(r"^[A-TV-Z]\d{2}(\.\d{1,4})?$"),
    "icd11": re.compile(r"^[0-9A-HJ-NP-Z][0-9A-HJ-NP-Z]\d[0-9A-HJ-NP-Z](\.[0-9A-HJ-NP-Z]{1,2})?$"),
    "icdo3": re.compile(r"^(C\d{2}(\.\d)?|M?\d{4}/\d)$"),
    "snomed": re.compile(r"^\d{6,18}$"),
    "icpc2": re.compile(r"^[A-Z]\d{2}$"),
    "nanda": re.compile(r"^\d{5}$"),
    "sdki": re.compile(r"^D\.\d{4}$"),
}


def normalize_system(value: Optional[str]) -> str:
    v = (value or "").lower().replace(" ", "").replace("-", "").replace("_", "")
    mapping = {
        "icd10": "icd10", "icd11": "icd11", "icdo3": "icdo3", "icdo": "icdo3",
        "snomed": "snomed", "snomedct": "snomed", "icpc2": "icpc2", "icpc": "icpc2",
        "nanda": "nanda", "nandai": "nanda", "sdki": "sdki", "lainnya": "lainnya",
    }
    return mapping.get(v, "icd10")


def normalize_code(system: str, code: Optional[str]) -> str:
    c = (code or "").strip()
    # buang awalan nama sistem bila ada, mis. "ICD-10 C40.2"
    c = re.sub(r"^(icd[\s-]?10|icd[\s-]?11|icd[\s-]?o[\s-]?3?|snomed(\s*ct)?|icpc[\s-]?2|nanda[\s-]?i?|sdki)\s*[:\-]?\s*", "", c, flags=re.I)
    c = c.split()[0] if c.split() else ""
    if system in ("icd10", "icd11", "icdo3", "icpc2"):
        c = c.upper()
    if system == "sdki":
        c = c.upper()
        if re.match(r"^D\d{4}$", c):
            c = "D." + c[1:]
    return c


def validate_format(system: str, code: Optional[str]) -> dict:
    """Mengembalikan {valid: bool|None, message: str}. None = tidak bisa divalidasi (sistem manual / kosong)."""
    code = normalize_code(system, code)
    if not code:
        return {"valid": None, "message": "No code entered."}
    pat = _PATTERNS.get(system)
    if pat is None:
        return {"valid": None, "message": "Manual system: format is not validated."}
    if pat.match(code):
        return {"valid": True, "message": "Code format is valid. Verify the code exists in the official release."}
    hint = next((s["hint"] for s in SYSTEMS if s["key"] == system), "")
    return {"valid": False, "message": f"Invalid format for {SYSTEM_LABEL.get(system, system)} ({hint})."}


# Daftar rujukan lokal ringkas: (kode, nama, kata kunci pencarian)
_LOCAL = {
    "icd10": [
        ("C40.2", "Neoplasma ganas tulang panjang tungkai bawah (mis. tibia, fibula, femur)", "osteosarkoma tibia femur fibula tulang panjang kanker tulang"),
        ("C41.9", "Neoplasma ganas tulang dan tulang rawan sendi, tidak spesifik", "osteosarkoma tulang kanker tulang"),
        ("C34.9", "Neoplasma ganas bronkus atau paru, tidak spesifik", "kanker paru lung cancer"),
        ("C50.9", "Neoplasma ganas payudara, tidak spesifik", "kanker payudara breast"),
        ("C71.9", "Neoplasma ganas otak, tidak spesifik", "tumor otak glioma brain"),
        ("D49.9", "Neoplasma perilaku tidak spesifik", "tumor massa neoplasma"),
        ("E11.9", "Diabetes melitus tipe 2 tanpa komplikasi", "diabetes melitus tipe 2 dm2 kencing manis"),
        ("E11.65", "Diabetes melitus tipe 2 dengan hiperglikemia", "diabetes tidak terkontrol hiperglikemia gds tinggi"),
        ("E11.5", "Diabetes melitus tipe 2 dengan komplikasi sirkulasi perifer", "diabetes komplikasi perifer ulkus kaki"),
        ("E78.5", "Hiperlipidemia, tidak spesifik", "dislipidemia kolesterol hiperlipidemia"),
        ("I10", "Hipertensi esensial (primer)", "hipertensi tekanan darah tinggi"),
        ("I11.9", "Penyakit jantung hipertensi tanpa gagal jantung", "hipertensi jantung"),
        ("I25.1", "Penyakit jantung aterosklerotik", "pjk penyakit jantung koroner"),
        ("I50.9", "Gagal jantung, tidak spesifik", "gagal jantung heart failure"),
        ("I63.9", "Infark serebral, tidak spesifik", "stroke iskemik infark serebri serebral mca"),
        ("I61.9", "Perdarahan intraserebral, tidak spesifik", "stroke hemoragik perdarahan otak ich"),
        ("I60.9", "Perdarahan subarachnoid, tidak spesifik", "sah perdarahan subarachnoid"),
        ("I51.7", "Kardiomegali", "kardiomegali jantung membesar"),
        ("J18.9", "Pneumonia, organisme tidak spesifik", "pneumonia radang paru"),
        ("J44.9", "Penyakit paru obstruktif kronik, tidak spesifik", "ppok copd"),
        ("J90", "Efusi pleura, tidak diklasifikasikan di tempat lain", "efusi pleura"),
        ("A15.0", "Tuberkulosis paru, terkonfirmasi", "tb paru tuberkulosis"),
        ("A16.2", "Tuberkulosis paru tanpa konfirmasi bakteriologis/histologis", "tb paru suspek tuberkulosis tbc radiologis"),
        ("A16.3", "Tuberkulosis kelenjar getah bening intratoraks, tanpa konfirmasi", "tb kelenjar hilus limfadenopati tuberkulosis"),
        ("A16.7", "Tuberkulosis respirasi primer, tanpa konfirmasi", "tb primer anak kompleks primer konsolidasi limfadenopati"),
        ("N18.3", "Penyakit ginjal kronik stadium 3", "ckd ginjal kronik stadium 3 egfr 45"),
        ("N18.5", "Penyakit ginjal kronik stadium 5", "ckd ginjal kronik stadium 5 gagal ginjal"),
        ("N20.0", "Batu ginjal", "nefrolitiasis batu ginjal"),
        ("K80.2", "Batu empedu tanpa kolesistitis", "kolelitiasis batu empedu"),
        ("K35.8", "Apendisitis akut lainnya dan tidak spesifik", "apendisitis usus buntu"),
        ("D64.9", "Anemia, tidak spesifik", "anemia hb rendah"),
        ("D50.9", "Anemia defisiensi besi, tidak spesifik", "anemia defisiensi besi"),
        ("M17.9", "Osteoartritis lutut, tidak spesifik", "oa lutut osteoartritis"),
        ("M54.5", "Nyeri punggung bawah", "low back pain nyeri punggung"),
        ("M81.9", "Osteoporosis, tidak spesifik", "osteoporosis"),
        ("S82.9", "Fraktur tungkai bawah, tidak spesifik", "fraktur tibia tungkai bawah patah tulang"),
        ("S72.9", "Fraktur femur, tidak spesifik", "fraktur femur patah tulang paha"),
        ("T14.8", "Cedera lain pada regio tubuh tidak spesifik", "fraktur cedera"),
        ("R91", "Temuan abnormal pada pencitraan paru", "nodul paru"),
        ("G93.6", "Edema serebral", "edema otak serebral"),
    ],
    "icd11": [
        ("5A11", "Diabetes melitus tipe 2", "diabetes melitus tipe 2 dm2"),
        ("BA00", "Hipertensi esensial", "hipertensi tekanan darah tinggi"),
        ("GB61", "Penyakit ginjal kronik", "ckd ginjal kronik"),
        ("8B11", "Stroke iskemik serebral", "stroke iskemik infark serebri"),
        ("CA40", "Pneumonia", "pneumonia radang paru"),
        ("1B10.0", "Tuberkulosis respirasi, terkonfirmasi", "tb paru tuberkulosis terkonfirmasi"),
        ("1B10.1", "Tuberkulosis respirasi, tidak terkonfirmasi", "tb paru suspek tuberkulosis tbc radiologis primer"),
        ("1B10.Z", "Tuberkulosis respirasi, tanpa keterangan konfirmasi", "tb paru tuberkulosis"),
        ("BD10", "Gagal jantung", "gagal jantung heart failure"),
    ],
    "icdo3": [
        ("C40.2", "Topografi: tulang panjang tungkai bawah", "osteosarkoma tibia femur tulang panjang"),
        ("M9180/3", "Morfologi: osteosarkoma NOS", "osteosarkoma"),
        ("M8000/3", "Morfologi: neoplasma ganas NOS", "tumor ganas neoplasma"),
    ],
    "snomed": [
        ("44054006", "Diabetes mellitus type 2 (disorder)", "diabetes melitus tipe 2"),
        ("38341003", "Hypertensive disorder, systemic arterial (disorder)", "hipertensi"),
        ("709044004", "Chronic kidney disease (disorder)", "ckd ginjal kronik"),
        ("230690007", "Cerebrovascular accident (disorder)", "stroke cva"),
        ("233604007", "Pneumonia (disorder)", "pneumonia"),
    ],
    "icpc2": [
        ("T90", "Diabetes tidak tergantung insulin", "diabetes melitus tipe 2"),
        ("K86", "Hipertensi tanpa komplikasi", "hipertensi"),
        ("K90", "Stroke atau kecelakaan serebrovaskular", "stroke cva"),
        ("R81", "Pneumonia", "pneumonia"),
    ],
    "nanda": [
        ("00132", "Nyeri akut (Acute pain)", "nyeri akut pain"),
        ("00133", "Nyeri kronis (Chronic pain)", "nyeri kronis"),
        ("00029", "Penurunan curah jantung (Decreased cardiac output)", "curah jantung"),
        ("00031", "Bersihan jalan napas tidak efektif", "jalan napas sekret"),
        ("00032", "Pola napas tidak efektif", "pola napas sesak"),
        ("00085", "Hambatan mobilitas fisik", "mobilitas fisik nyeri tulang fraktur"),
        ("00004", "Risiko infeksi", "infeksi luka operasi"),
        ("00155", "Risiko jatuh", "jatuh"),
        ("00046", "Kerusakan integritas kulit", "luka kulit integritas"),
        ("00179", "Risiko ketidakstabilan kadar glukosa darah", "glukosa diabetes gula darah"),
        ("00126", "Defisiensi pengetahuan", "pengetahuan edukasi"),
        ("00146", "Ansietas", "cemas ansietas"),
        ("00092", "Intoleransi aktivitas", "aktivitas lemah"),
        ("00026", "Kelebihan volume cairan", "hipervolemia edema ginjal"),
        ("00027", "Kekurangan volume cairan", "hipovolemia dehidrasi"),
        ("00201", "Risiko perfusi jaringan serebral tidak efektif", "serebral stroke otak perfusi"),
        ("00204", "Perfusi jaringan perifer tidak efektif", "perfusi perifer"),
        ("00007", "Hipertermia", "demam hipertermia"),
    ],
    "sdki": [
        ("D.0077", "Nyeri akut", "nyeri akut"),
        ("D.0078", "Nyeri kronis", "nyeri kronis"),
        ("D.0008", "Penurunan curah jantung", "curah jantung"),
        ("D.0001", "Bersihan jalan napas tidak efektif", "jalan napas sekret"),
        ("D.0005", "Pola napas tidak efektif", "pola napas sesak"),
        ("D.0054", "Gangguan mobilitas fisik", "mobilitas fisik nyeri tulang fraktur"),
        ("D.0142", "Risiko infeksi", "infeksi luka operasi"),
        ("D.0143", "Risiko jatuh", "jatuh"),
        ("D.0129", "Gangguan integritas kulit atau jaringan", "luka kulit integritas"),
        ("D.0027", "Ketidakstabilan kadar glukosa darah", "glukosa diabetes gula darah"),
        ("D.0111", "Defisit pengetahuan", "pengetahuan edukasi"),
        ("D.0080", "Ansietas", "cemas ansietas"),
        ("D.0056", "Intoleransi aktivitas", "aktivitas lemah"),
        ("D.0022", "Hipervolemia", "hipervolemia edema ginjal"),
        ("D.0023", "Hipovolemia", "hipovolemia dehidrasi"),
        ("D.0017", "Risiko perfusi serebral tidak efektif", "serebral stroke otak perfusi"),
        ("D.0009", "Perfusi perifer tidak efektif", "perfusi perifer"),
        ("D.0019", "Defisit nutrisi", "nutrisi gizi"),
        ("D.0130", "Hipertermia", "demam hipertermia"),
        ("D.0109", "Defisit perawatan diri", "perawatan diri mandi"),
    ],
}


def search_local(system: str, query: str, limit: int = 12) -> List[dict]:
    items = _LOCAL.get(system, [])
    q = (query or "").lower().strip()
    out = []
    for code, name, kw in items:
        hay = f"{code} {name} {kw}".lower()
        if not q:
            score = 1
        else:
            terms = [t for t in q.split() if t]
            hits = sum(1 for t in terms if t in hay)
            if hits == 0:
                continue
            score = hits
        out.append((score, {"system": system, "code": code, "name": name}))
    out.sort(key=lambda x: -x[0])
    return [o[1] for o in out[:limit]]


def best_local_match(system: str, text: str) -> Optional[dict]:
    """Cocokkan teks diagnosis bebas ke satu entri lokal (jumlah kata kunci cocok terbanyak, minimal 1)."""
    low = (text or "").lower()
    if not low:
        return None
    best, best_hits = None, 0
    for code, name, kw in _LOCAL.get(system, []):
        words = set((kw + " " + name).lower().split())
        hits = sum(1 for w in words if len(w) > 3 and w in low)
        if hits > best_hits:
            best, best_hits = {"system": system, "code": code, "name": name}, hits
    return best if best_hits >= 2 else None
