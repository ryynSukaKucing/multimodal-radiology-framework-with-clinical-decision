"""Sinkronisasi diagnosis dengan lesi yang LOLOS koreksi geometri.

Setelah kotak/kontur dikoreksi, sebagian lesi dapat dibuang (letak salah, bayangan jaringan lunak, dst). Fungsi ini memeriksa apakah tiap
penyakit pada diagnosis utama masih punya temuan pendukung di 'anomalies'. Bila tidak, diagnosis TIDAK diganti (menimpa diagnosis dengan
gabungan label lesi menghilangkan makna klinis, mis. "Heart failure" menjadi "Right pleural effusion"): keyakinan diturunkan,
`diagnosis_perlu_verifikasi` diset, dan deskripsi temuan tervalidasi ditambahkan ke diagnosis banding.
"""
import re
from typing import List, Optional

from ..thorax_anatomy_taxonomy import side_of_text

# (regex pada diagnosis, regex temuan pendukung yang harus ada pada 'anomalies', nama untuk catatan)
_RULES = (
    (re.compile(r"(pneumonia|pneumonitis|bronkopneumonia|bronchopneumonia|pneumonitis)", re.I),
     re.compile(r"(konsolidasi|consolidation|infiltrat|opasitas|opacity|airspace)", re.I), "pneumonia"),
    (re.compile(r"(efusi|effusion|hidrotoraks|hydrothorax|empyema|empiema)", re.I),
     re.compile(r"(efusi|effusion|meniscus|costophrenic|kostofrenikus|basal opacity)", re.I), "pleural effusion"),
    (re.compile(r"(kardiomegali|cardiomegaly|cardiac enlargement|pembesaran jantung)", re.I),
     re.compile(r"(kardiomegali|cardiomegaly|cardiac|jantung|heart)", re.I), "cardiomegaly"),
    (re.compile(r"(edema paru|pulmonary (?:o)?edema|gagal jantung|heart failure|congestive)", re.I),
     re.compile(r"(edema|oedema|perihilar|kardiomegali|cardiomegaly|kerley|butterfly)", re.I), "pulmonary oedema"),
    (re.compile(r"(pneumotoraks|pneumothorax)", re.I), re.compile(r"(pneumotoraks|pneumothorax|pleural line)", re.I), "pneumothorax"),
    (re.compile(r"(atelektasis|atelectasis|kolaps|collapse|volume loss)", re.I),
     re.compile(r"(atelektasis|atelectasis|kolaps|collapse|volume loss|opasitas|opacity)", re.I), "atelectasis"),
    (re.compile(r"(tuberkulosis|tuberculosis|\bTB\b|granulomatous|granulomatosa)", re.I),
     re.compile(r"(kavitas|cavit|apical|apeks|apex|fibrosis|milier|miliary|konsolidasi|consolidation|infiltrat|nodul|nodule|hil(?:us|um|ar)|limfadenopati|lymphaden)", re.I),
     "granulomatous infection"),
    (re.compile(r"(massa|mass\b|malignan|karsinoma|carcinoma|tumor|neoplasm|kanker|cancer)", re.I),
     re.compile(r"(massa|mass\b|nodul|nodule|hil(?:us|um|ar)|mediastin|paratrakeal|paratracheal|opasitas|opacity)", re.I), "mass or malignancy"),
    (re.compile(r"(nodul|nodule)", re.I), re.compile(r"(nodul|nodule|massa|mass\b)", re.I), "nodule"),
    (re.compile(r"(fibrosis|interstitial|interstisial)", re.I), re.compile(r"(fibrosis|reticul|interstitial|interstisial)", re.I), "fibrosis"),
    (re.compile(r"(limfadenopati|lymphadenopath|pembesaran hil|hilar enlargement|hil(?:us|um|ar)[a-z ]{0,20}(?:prominen|nodul|mass|massa|bulk))", re.I),
     re.compile(r"(hil(?:us|um|ar)|paratrakeal|paratracheal|mediastin|limfadenopati|lymphaden)", re.I), "hilar or mediastinal enlargement"),
    (re.compile(r"(basal|lower[- ]zone|zona bawah)[a-z ]{0,20}(?:opacity|opasitas|haz)", re.I),
     re.compile(r"(opasitas|opacity|haz|efusi|effusion|costophrenic|kostofrenikus|konsolidasi|consolidation|atelektasis|atelectasis|basal)", re.I), "basal opacity"),
)

_NORMAL = re.compile(r"(normal|tidak (?:ada|tampak) kelainan|no (?:significant )?abnormalit|unremarkable|no acute)", re.I)


def _lesion_text(a: dict) -> str:
    return f"{a.get('label', '')} {a.get('description', '')}"


def _clean_label(label: str) -> str:
    return re.sub(r"\s+", " ", str(label or "")).strip().rstrip(".")


_SIDE_WORDS = r"(?:right|left|kanan|kiri|bilateral|both|kedua)"
_ZONE_WORDS = r"(?:apical|apex|apeks|upper|middle|mid|lower|basal|atas|tengah|bawah|perihilar|peri-hilar)"
_TRAIL_SIDE = re.compile(r"\s+(?:in|at|of|on|within|di|pada)\s+(?:the\s+)?" + _SIDE_WORDS + r"\b.*$", re.I)
_TRAIL_ZONE = re.compile(r"\s+(?:in|at|of|on|within|di|pada)\s+(?:the\s+)?(?:(?:right|left|kanan|kiri)\s+)?(?:upper|middle|mid|lower|apical|basal|atas|tengah|bawah)\s+(?:zones?|lobes?|lung fields?|lapang|zona|lobus)\b.*$", re.I)
_PAREN = re.compile(r"\s*\([^)]*\)")
_SIDE_ONLY = re.compile(r"\b" + _SIDE_WORDS + r"\b", re.I)
_BILAT = re.compile(r"\b(?:bilateral|both|kedua)\b", re.I)
_DANGLING = re.compile(r"\s+(?:in|at|of|on|within|the|di|pada)\s*$", re.I)
_ZONE_PREFIX = re.compile(r"\b(?:upper|middle|mid|lower|apical|basal)\s+(?:zone|lobe)\s+", re.I)


def _kind_and_side(label: str):
    """(jenis temuan tanpa sisi/zona, sisi 'right'/'left'/'bilateral'/None). Dipakai untuk menggabungkan label sejenis."""
    raw = _clean_label(label)
    side = None
    if _BILAT.search(raw):
        side = "bilateral"
    else:
        st = side_of_text(raw)
        side = {"R": "right", "L": "left"}.get(st)
    core = _PAREN.sub("", raw)
    core = _TRAIL_ZONE.sub("", core)
    core = _TRAIL_SIDE.sub("", core)
    core = _ZONE_PREFIX.sub("", core)
    core = _SIDE_ONLY.sub("", core)
    core = re.sub(r"\s+", " ", core).strip(" ,;-")
    core = _DANGLING.sub("", core).strip(" ,;-")
    return (core or raw), side


def describe_findings(anomalies: list, limit: int = 3) -> str:
    """Deskripsi temuan dari lesi yang tersisa: label sejenis digabung (sisi/zona dibuang dari label, sisi ditulis SEKALI),
    mis. dua lesi 'perihilar congestion' kiri + kanan -> 'bilateral perihilar congestion'. Urut skor keparahan, tanpa duplikat."""
    ranked = sorted((a for a in anomalies if a.get("box") or a.get("polygon")), key=lambda a: -float(a.get("severity_score") or 0))
    groups: dict = {}
    order: List[str] = []
    for a in ranked:
        core, side = _kind_and_side(a.get("label"))
        if not core:
            continue
        key = core.lower()
        if key not in groups:
            groups[key] = {"core": core, "sides": set()}
            order.append(key)
        if side:
            groups[key]["sides"].add(side)
    phrases = []
    for key in order[:limit]:
        g = groups[key]
        sides = g["sides"]
        core = g["core"]
        if "bilateral" in sides or {"right", "left"} <= sides:
            side_txt = "bilateral"
        elif len(sides) == 1:
            side_txt = next(iter(sides))
        else:
            side_txt = ""
        if side_txt:
            core = (core[0].lower() + core[1:]) if core[1:2].islower() else core
            phrases.append(f"{side_txt} {core}")
        else:
            phrases.append(core)
    if not phrases:
        return ""
    phrases[0] = phrases[0][0].upper() + phrases[0][1:]
    if len(phrases) == 1:
        return phrases[0]
    tail = [(t[0].lower() + t[1:]) if t[1:2].islower() else t for t in phrases[1:]]
    return phrases[0] + " with " + (", ".join(tail[:-1]) + " and " + tail[-1] if len(tail) > 1 else tail[0])


def _side_conflict(diag: str, kept: list) -> Optional[str]:
    """Diagnosis menyebut SATU sisi (mis. 'left basal opacity') tetapi semua lesi bersisi di sisi lain: kotak tidak menunjuk temuan yang didiagnosis."""
    dsides = set()
    for m in re.finditer(r"\b(right|kanan|left|kiri)\b", diag, re.I):
        dsides.add("R" if m.group(1).lower() in ("right", "kanan") else "L")
    if len(dsides) != 1 or re.search(r"\b(bilateral|both|kedua)\b", diag, re.I):
        return None
    want = next(iter(dsides))
    sides = set()
    for a in kept:
        t = _lesion_text(a)
        if re.search(r"\b(bilateral|both|kedua)\b", t, re.I) or re.search(r"(cardiomegal|kardiomegal|cardiac|jantung|heart|mediastin)", t, re.I):
            return None
        s = side_of_text(a.get("label", "")) or side_of_text(a.get("description", ""))
        if s:
            sides.add(s)
    if sides and want not in sides:
        word = {"R": "right", "L": "left"}[want]
        return (f"The diagnosis names a {word}-sided finding, but every boxed lesion is on the other side; the {word} finding has no box. "
                "Please verify manually or re-scan.")
    return None


def sync_diagnosis_with_findings(result: dict, anomalies: list, dropped: Optional[List[str]] = None) -> Optional[str]:
    """Samakan diagnosis dengan lesi yang tersisa (mengubah `result` di tempat). Mengembalikan catatan atau None."""
    diag = str(result.get("diagnosis") or "").strip()
    dropped = [d for d in (dropped or []) if d]
    kept = [a for a in anomalies or [] if a.get("box") or a.get("polygon")]
    if not diag:
        return None
    support = " ".join(_lesion_text(a) for a in kept)

    unsupported = [name for dx_rx, need_rx, name in _RULES if dx_rx.search(diag) and not need_rx.search(support)]
    if not unsupported:
        conflict = _side_conflict(diag, kept) if kept else None
        if conflict:
            result["confidence"] = min(float(result.get("confidence") or 0), 0.5)
            result["diagnosis_perlu_verifikasi"] = True
            result["catatan_sinkron"] = conflict
            return conflict
        if dropped:
            result["catatan_sinkron"] = f"{len(dropped)} finding(s) were removed because their location was not valid; the diagnosis is still supported by the remaining findings."
            return result["catatan_sinkron"]
        return None

    note = None
    if kept:
        # Pertahankan diagnosis; turunkan keyakinan, minta verifikasi, dan simpan deskripsi temuan sebagai alternatif.
        result["confidence"] = min(float(result.get("confidence") or 0), 0.5)
        result["diagnosis_perlu_verifikasi"] = True
        alts = [a for a in (result.get("diagnosis_alternatif") or []) if isinstance(a, str)]
        desc = describe_findings(kept)
        if desc and desc.lower() not in [x.lower() for x in alts]:
            alts.insert(0, desc)
        result["diagnosis_alternatif"] = alts[:8]
        note = (f"Diagnosis '{diag}' belum didukung temuan tervalidasi ({', '.join(unsupported)}); "
                "keyakinan diturunkan, mohon verifikasi manual.")
    elif unsupported and not dropped:
        # model menyebut temuan di diagnosis tetapi tidak pernah melaporkan lesinya (anomalies kosong): jangan lolos diam-diam
        result["confidence"] = min(float(result.get("confidence") or 0), 0.4)
        result["diagnosis_perlu_verifikasi"] = True
        note = (f"Diagnosis '{diag}' menyebut temuan ({', '.join(unsupported)}) tetapi tidak ada lesi bertanda lokasi pada citra; "
                "keyakinan diturunkan, mohon verifikasi manual.")
    elif dropped and (not _NORMAL.search(diag) or unsupported):
        result["confidence"] = min(float(result.get("confidence") or 0), 0.4)
        note = ("All lesions reported by the model were removed because their location was invalid; the diagnosis could not be "
                "confirmed on the image and confidence was lowered. Please re-scan or review manually.")
    if note:
        result["catatan_sinkron"] = note
    return note
