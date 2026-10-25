"""Pemeriksaan konsistensi diagnosis vs temuan (umum). Tidak mengganti diagnosis utama; hanya menambah banding dan membatasi keyakinan."""
import re
from typing import Optional, Tuple

_NEG = re.compile(r"(tanpa|tidak (?:ada|tampak|terlihat|didapatkan)|bukan|no |without|absent|negative|normal|not seen|no evidence of)[^.;,\n]{0,28}$", re.I)

# Findings that are NOT typical for a specific diagnosis -> differential diagnoses worth adding.
# (finding name, regex, suggested differential diagnoses)
_ATYPICAL = (
    ("hilar or mediastinal lymphadenopathy/enlargement",
     re.compile(r"(limfadenopati|lymphadenopath|pembesaran (?:kgb|kelenjar)|hil(?:us|um|ar) (?:kanan|kiri|right|left)?\s*(?:melebar|membesar|prominen|lobulated|enlarge|prominen|widen)|"
                r"(?:pelebaran|enlargement|widening) (?:of )?(?:hilus|hilum|hilar|mediastinum)|massa paratrakeal|paratracheal (?:mass|node)|nodus (?:hilus|paratrakeal))", re.I),
     ["Granulomatous infection (e.g. pulmonary tuberculosis)", "Lung malignancy with nodal metastasis"]),
    ("cavity", re.compile(r"(kavitas|cavit)", re.I),
     ["Granulomatous infection (e.g. pulmonary tuberculosis)", "Lung abscess", "Cavitating lung malignancy"]),
    ("satellite nodules / tree-in-bud", re.compile(r"(tree[- ]in[- ]bud|nodul satelit|satellite nodul)", re.I),
     ["Granulomatous infection (e.g. pulmonary tuberculosis)"]),
    ("miliary pattern", re.compile(r"(milier|miliary)", re.I), ["Miliary tuberculosis", "Miliary metastases"]),
    ("solitary mass/nodule", re.compile(r"(?:(?:massa|nodul)\s+(?:soliter|spikulasi|spiculated)|(?:solitary|spiculated)\s+(?:mass|nodule)|spikulasi|spiculation)", re.I),
     ["Lung malignancy", "Granuloma/infection"]),
)

# Very specific diagnoses that are easily overused.
_SPECIFIC_DX = re.compile(r"(pneumonia\s+lobaris|lobar\s+pneumonia|pneumonia\s+lobar|pneumonia\s+segmental|segmental\s+pneumonia)", re.I)

CONF_CAP_AMBIGU = 0.75
CONF_CAP_TANPA_BANDING = 0.80


def _positive_hits(text: str):
    """(nama temuan, banding) untuk temuan atipikal yang disebut TANPA kata penyangkal di depannya."""
    found = []
    for name, rx, alts in _ATYPICAL:
        for m in rx.finditer(text):
            before = text[max(0, m.start() - 40):m.start()]
            if not _NEG.search(before):
                found.append((name, alts))
                break
    return found


def _result_text(result: dict) -> str:
    parts = [str(result.get("summary") or "")]
    for a in result.get("anomalies") or []:
        parts.append(f"{a.get('label', '')}. {a.get('description', '')}.")
    return " \n".join(parts)


def reconcile_thorax_diagnosis(result: dict) -> Tuple[dict, Optional[str]]:
    """Cek konsistensi umum antara diagnosis dan temuan yang model laporkan sendiri.

    TIDAK mengganti diagnosis utama. Hanya: (1) menambahkan diagnosis banding yang relevan bila temuan atipikal untuk
    diagnosis spesifik, (2) membatasi keyakinan yang tidak wajar. Mengembalikan (result, catatan|None).
    """
    diag = str(result.get("diagnosis") or "")
    alts = list(result.get("diagnosis_alternatif") or [])
    notes = []

    if _SPECIFIC_DX.search(diag):
        hits = _positive_hits(_result_text(result))
        if hits:
            have = " ".join(alts).lower()
            added = []
            for _, cand in hits:
                for c in cand:
                    key = c.split("(")[0].strip().lower()
                    if key and key not in have and c not in added:
                        added.append(c)
            alts = alts + added
            result["confidence"] = min(float(result.get("confidence") or 0), CONF_CAP_AMBIGU)
            notes.append("Finding(s) " + ", ".join(h[0] for h in hits) + " are not typical for '" + diag
                         + "'; differential diagnoses were added and confidence was capped.")

    if not alts and float(result.get("confidence") or 0) > CONF_CAP_TANPA_BANDING:
        result["confidence"] = CONF_CAP_TANPA_BANDING
        notes.append("Confidence was capped because there is no differential diagnosis.")

    main = str(result.get("diagnosis") or "").strip().lower()
    seen, clean = set(), []
    for x in alts:
        k = str(x).strip().lower()
        if k and k != main and k not in seen:
            seen.add(k)
            clean.append(x)
    result["diagnosis_alternatif"] = clean[:8]

    note = " ".join(notes) or None
    if note:
        result["catatan_konsistensi"] = note
    return result, note
