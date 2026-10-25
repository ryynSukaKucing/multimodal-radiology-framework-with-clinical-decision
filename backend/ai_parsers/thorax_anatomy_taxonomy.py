"""Thorax_Anatomy_Taxonomy: satu-satunya sumber kebenaran untuk label anatomi toraks.

Dipakai oleh: prompt deteksi/segmentasi anatomi (daftar id yang boleh), parser (label model -> id baku),
koreksi geometri (sisi kiri/kanan, kewajaran posisi, zona paru), dan viewer (warna + pengelompokan legenda).

Struktur `THORAX_ANATOMY_TAXONOMY` sama persis dengan taksonomi yang ditetapkan; nama pada daftar adalah `id` baku.
Tambahan di luar daftar daun taksonomi hanya induk yang sah sebagai satu objek utuh:
`right_lung`, `left_lung` (lapang paru utuh), `cardiac_silhouette` dan `mediastinum`.
"""
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

THORAX_ANATOMY_TAXONOMY = {
    "respiratory_system": {
        "airway": ["trachea", "carina", "right_main_bronchus", "left_main_bronchus"],
        "lungs": {
            "right_lung": ["right_upper_lobe", "right_middle_lobe", "right_lower_lobe"],
            "left_lung": ["left_upper_lobe", "left_lingula", "left_lower_lobe"],
        },
        "fissures": ["horizontal_fissure", "oblique_fissure_right", "oblique_fissure_left"],
        "zones": ["apex_right", "apex_left", "upper_zone_right", "upper_zone_left", "middle_zone_right",
                  "middle_zone_left", "lower_zone_right", "lower_zone_left"],
    },
    "cardiovascular_and_mediastinum": {
        "hilar_region": ["right_hilum", "left_hilum"],
        "cardiac_silhouette": ["right_atrium_border", "left_ventricle_border", "apex_cordis"],
        "vascular_structures": ["aortic_knob", "ascending_aorta", "descending_aorta", "superior_vena_cava",
                                "main_pulmonary_artery"],
        "mediastinum": ["superior_mediastinum", "anterior_mediastinum", "posterior_mediastinum"],
    },
    "pleura_and_diaphragm": {
        "diaphragm": ["right_hemidiaphragm", "left_hemidiaphragm"],
        "angles": ["right_costophrenic_angle", "left_costophrenic_angle", "right_cardiophrenic_angle",
                   "left_cardiophrenic_angle"],
    },
    "skeletal_system": {
        "clavicles": ["right_clavicle", "left_clavicle"],
        "ribs": ["ribs_posterior_1_to_12", "ribs_anterior_1_to_6"],
        "spine": ["thoracic_vertebrae_T1_T12", "intervertebral_spaces"],
        "other_bones": ["sternum", "right_scapula", "left_scapula"],
    },
    "soft_tissue_and_abdominal": ["breast_shadow", "gastric_air_bubble", "subcutaneous_tissue"],
}

SYSTEM_LABEL = {
    "respiratory_system": "Respiratory System",
    "cardiovascular_and_mediastinum": "Cardiovascular & Mediastinum",
    "pleura_and_diaphragm": "Pleura & Diaphragm",
    "skeletal_system": "Skeletal System",
    "soft_tissue_and_abdominal": "Soft Tissue & Abdominal",
}
GROUP_LABEL = {
    "airway": "Airway", "lungs": "Lungs & lobes", "fissures": "Fissures", "zones": "Lung zones",
    "hilar_region": "Hila", "cardiac_silhouette": "Cardiac silhouette", "vascular_structures": "Great vessels",
    "mediastinum": "Mediastinum", "diaphragm": "Diaphragm", "angles": "Pleural angles", "clavicles": "Clavicles",
    "ribs": "Ribs", "spine": "Spine", "other_bones": "Other bones", "soft_tissue_and_abdominal": "Soft tissue",
}

# Warna per grup (sisi kanan, sisi kiri, garis tengah/bilateral). Satu sumber untuk overlay dan legenda.
GROUP_COLOR = {
    "airway": ("#fbbf24", "#f59e0b", "#fcd34d"),
    "lungs": ("#38bdf8", "#34d399", "#7dd3fc"),
    "fissures": ("#e0f2fe", "#d1fae5", "#e2e8f0"),
    "zones": ("#0ea5e9", "#10b981", "#94a3b8"),
    "hilar_region": ("#2dd4bf", "#a3e635", "#5eead4"),
    "cardiac_silhouette": ("#f472b6", "#ec4899", "#f9a8d4"),
    "vascular_structures": ("#fb923c", "#f97316", "#fdba74"),
    "mediastinum": ("#a78bfa", "#8b5cf6", "#c4b5fd"),
    "diaphragm": ("#a1a1aa", "#e4e4e7", "#d4d4d8"),
    "angles": ("#fb7185", "#f43f5e", "#fda4af"),
    "clavicles": ("#fde68a", "#fef08a", "#fef3c7"),
    "ribs": ("#d6d3d1", "#e7e5e4", "#d6d3d1"),
    "spine": ("#fcd34d", "#fbbf24", "#fde047"),
    "other_bones": ("#fef9c3", "#fde68a", "#fef08a"),
    "soft_tissue_and_abdominal": ("#a5b4fc", "#67e8f9", "#94a3b8"),
}

# Baris registri: id, label Indonesia, label Inggris, sisi (R/L/M/B), bentuk (polygon/line/box/point), tingkat prioritas
# (1 inti, 2 sekunder, 3 opsional), jendela kewajaran posisi dalam koordinat lapang pandang 0..1:
# (cx_min, cx_max, cy_min, cy_max, lebar_maks, tinggi_maks), alias tambahan. Sisi R = kanan pasien = sisi KIRI gambar (PA/AP).
_ROWS = [
    # --- Sistem respirasi: jalan napas
    ("trachea", "Trakea", "Trachea", "M", "polygon", 1, (.36, .64, .06, .5, .16, .65), ["windpipe"]),
    ("carina", "Karina", "Carina", "M", "point", 2, (.36, .64, .12, .6, .14, .14), []),
    ("right_main_bronchus", "Bronkus utama kanan", "Right main bronchus", "R", "box", 2, (.26, .52, .18, .6, .32, .28), []),
    ("left_main_bronchus", "Bronkus utama kiri", "Left main bronchus", "L", "box", 2, (.48, .74, .18, .6, .32, .28), []),
    # --- lapang paru dan lobus
    ("right_lung", "Paru kanan", "Right lung", "R", "polygon", 1, (.08, .47, .1, .92, .54, 1.0), ["lapang paru kanan"]),
    ("left_lung", "Paru kiri", "Left lung", "L", "polygon", 1, (.53, .92, .1, .92, .54, 1.0), ["lapang paru kiri"]),
    ("right_upper_lobe", "Lobus atas kanan", "Right upper lobe", "R", "polygon", 3, (.08, .47, 0, .58, .54, .75), ["rul", "lobus superior kanan"]),
    ("right_middle_lobe", "Lobus tengah kanan", "Right middle lobe", "R", "polygon", 3, (.1, .5, .28, .8, .5, .55), ["rml", "lobus medius kanan"]),
    ("right_lower_lobe", "Lobus bawah kanan", "Right lower lobe", "R", "polygon", 3, (.08, .5, .32, 1.0, .5, .8), ["rll", "lobus inferior kanan"]),
    ("left_upper_lobe", "Lobus atas kiri", "Left upper lobe", "L", "polygon", 3, (.5, .92, 0, .68, .54, .85), ["lul", "lobus superior kiri"]),
    ("left_lingula", "Lingula kiri", "Left lingula", "L", "polygon", 3, (.5, .88, .32, .85, .46, .55), ["lingula"]),
    ("left_lower_lobe", "Lobus bawah kiri", "Left lower lobe", "L", "polygon", 3, (.5, .92, .32, 1.0, .5, .8), ["lll", "lobus inferior kiri"]),
    # --- fisura
    ("horizontal_fissure", "Fisura horizontal", "Horizontal fissure", "R", "line", 3, (.08, .5, .22, .68, .5, .22), ["minor fissure", "fisura minor"]),
    ("oblique_fissure_right", "Fisura oblik kanan", "Right oblique fissure", "R", "line", 3, (.08, .5, .18, .95, .5, .85), ["major fissure kanan"]),
    ("oblique_fissure_left", "Fisura oblik kiri", "Left oblique fissure", "L", "line", 3, (.5, .92, .18, .95, .5, .85), ["major fissure kiri"]),
    # --- zona paru (umumnya diturunkan otomatis dari kontur paru)
    ("apex_right", "Apeks paru kanan", "Right lung apex", "R", "polygon", 3, (.08, .48, 0, .32, .5, .35), ["apeks kanan", "apikal kanan"]),
    ("apex_left", "Apeks paru kiri", "Left lung apex", "L", "polygon", 3, (.52, .92, 0, .32, .5, .35), ["apeks kiri", "apikal kiri"]),
    ("upper_zone_right", "Zona atas paru kanan", "Right upper zone", "R", "polygon", 3, (.08, .48, .02, .5, .5, .5), []),
    ("upper_zone_left", "Zona atas paru kiri", "Left upper zone", "L", "polygon", 3, (.52, .92, .02, .5, .5, .5), []),
    ("middle_zone_right", "Zona tengah paru kanan", "Right middle zone", "R", "polygon", 3, (.08, .48, .25, .75, .5, .5), []),
    ("middle_zone_left", "Zona tengah paru kiri", "Left middle zone", "L", "polygon", 3, (.52, .92, .25, .75, .5, .5), []),
    ("lower_zone_right", "Zona bawah paru kanan", "Right lower zone", "R", "polygon", 3, (.08, .48, .45, 1.0, .5, .55), []),
    ("lower_zone_left", "Zona bawah paru kiri", "Left lower zone", "L", "polygon", 3, (.52, .92, .45, 1.0, .5, .55), []),
    # --- kardiovaskular & mediastinum
    ("right_hilum", "Hilus kanan", "Right hilum", "R", "polygon", 1, (.26, .5, .2, .65, .28, .38), []),
    ("left_hilum", "Hilus kiri", "Left hilum", "L", "polygon", 1, (.5, .74, .16, .6, .28, .38), []),
    ("cardiac_silhouette", "Siluet jantung", "Cardiac silhouette", "M", "polygon", 1, (.3, .78, .38, .96, .6, .62), ["heart shadow", "bayangan jantung"]),
    ("right_atrium_border", "Tepi atrium kanan", "Right atrium border", "R", "line", 2, (.26, .54, .42, .94, .2, .5), ["tepi kanan jantung"]),
    ("left_ventricle_border", "Tepi ventrikel kiri", "Left ventricle border", "L", "line", 2, (.5, .84, .45, .96, .3, .5), ["tepi kiri jantung"]),
    ("apex_cordis", "Apeks jantung", "Cardiac apex", "L", "point", 2, (.5, .9, .58, 1.0, .18, .22), ["apex jantung", "cardiac apex"]),
    ("aortic_knob", "Knob aorta", "Aortic knob", "M", "box", 2, (.4, .72, .04, .44, .24, .24), ["arkus aorta", "aortic arch", "arkus aortae"]),
    ("ascending_aorta", "Aorta asendens", "Ascending aorta", "M", "line", 3, (.3, .64, .08, .52, .24, .5), ["aorta asenden"]),
    ("descending_aorta", "Aorta desendens", "Descending aorta", "M", "line", 3, (.4, .7, .18, .95, .22, .8), ["aorta desenden", "aorta torakalis"]),
    ("superior_vena_cava", "Vena kava superior", "Superior vena cava", "R", "line", 3, (.26, .54, 0, .46, .16, .46), ["svc", "vena cava superior"]),
    ("main_pulmonary_artery", "Arteri pulmonalis utama", "Main pulmonary artery", "M", "box", 3, (.4, .7, .18, .54, .26, .28), ["pulmonary trunk", "truncus pulmonalis", "segmen pulmonal"]),
    ("mediastinum", "Mediastinum", "Mediastinum", "M", "polygon", 1, (.28, .72, 0, .96, .44, 1.0), []),
    ("superior_mediastinum", "Mediastinum superior", "Superior mediastinum", "M", "polygon", 3, (.28, .72, .06, .42, .44, .48), []),
    ("anterior_mediastinum", "Mediastinum anterior", "Anterior mediastinum", "M", "polygon", 3, (.28, .72, .15, .85, .44, .7), []),
    ("posterior_mediastinum", "Mediastinum posterior", "Posterior mediastinum", "M", "polygon", 3, (.28, .72, .15, .95, .44, .8), []),
    # --- pleura & diafragma
    ("right_hemidiaphragm", "Diafragma kanan", "Right hemidiaphragm", "R", "line", 1, (.06, .5, .55, 1.02, .52, .36), ["hemidiafragma kanan"]),
    ("left_hemidiaphragm", "Diafragma kiri", "Left hemidiaphragm", "L", "line", 1, (.5, .94, .55, 1.02, .52, .36), ["hemidiafragma kiri"]),
    ("right_costophrenic_angle", "Sudut kostofrenikus kanan", "Right costophrenic angle", "R", "point", 2, (.02, .42, .62, 1.02, .22, .22), ["sinus kostofrenikus kanan"]),
    ("left_costophrenic_angle", "Sudut kostofrenikus kiri", "Left costophrenic angle", "L", "point", 2, (.58, .98, .62, 1.02, .22, .22), ["sinus kostofrenikus kiri"]),
    ("right_cardiophrenic_angle", "Sudut kardiofrenikus kanan", "Right cardiophrenic angle", "R", "point", 2, (.26, .54, .62, 1.02, .18, .18), []),
    ("left_cardiophrenic_angle", "Sudut kardiofrenikus kiri", "Left cardiophrenic angle", "L", "point", 2, (.46, .78, .62, 1.02, .18, .18), []),
    # --- tulang
    ("right_clavicle", "Klavikula kanan", "Right clavicle", "R", "line", 2, (.04, .52, 0, .42, .56, .22), []),
    ("left_clavicle", "Klavikula kiri", "Left clavicle", "L", "line", 2, (.48, .96, 0, .42, .56, .22), []),
    ("ribs_posterior_1_to_12", "Iga posterior 1-12", "Posterior ribs 1-12", "B", "box", 3, (0, 1, 0, 1, 1.05, 1.05), ["iga posterior", "kosta posterior", "posterior ribs"]),
    ("ribs_anterior_1_to_6", "Iga anterior 1-6", "Anterior ribs 1-6", "B", "box", 3, (0, 1, 0, 1, 1.05, 1.05), ["iga anterior", "kosta anterior", "anterior ribs"]),
    ("thoracic_vertebrae_T1_T12", "Vertebra torakal T1-T12", "Thoracic vertebrae T1-T12", "M", "box", 2, (.36, .64, 0, 1.0, .22, 1.05), ["tulang belakang", "spine", "kolumna vertebralis"]),
    ("intervertebral_spaces", "Ruang intervertebralis", "Intervertebral spaces", "M", "box", 3, (.36, .64, 0, 1.0, .22, 1.05), ["diskus intervertebralis", "intervertebral disc"]),
    ("sternum", "Sternum", "Sternum", "M", "box", 3, (.36, .64, 0, .75, .22, .75), ["tulang dada"]),
    ("right_scapula", "Skapula kanan", "Right scapula", "R", "box", 3, (0, .36, 0, .85, .42, .85), []),
    ("left_scapula", "Skapula kiri", "Left scapula", "L", "box", 3, (.64, 1, 0, .85, .42, .85), []),
    # --- jaringan lunak & abdomen
    ("breast_shadow", "Bayangan payudara", "Breast shadow", "B", "box", 3, (0, 1, .4, 1.05, 1.05, .65), ["payudara", "mamma"]),
    ("gastric_air_bubble", "Gelembung gas lambung", "Gastric air bubble", "L", "box", 2, (.48, .96, .62, 1.05, .42, .4), ["gastric bubble", "magenblase", "gelembung lambung"]),
    ("subcutaneous_tissue", "Jaringan subkutan", "Subcutaneous tissue", "B", "box", 3, (0, 1, 0, 1.05, 1.05, 1.05), ["jaringan lunak dinding dada", "subkutis"]),
]

_PARENT_IDS = ("right_lung", "left_lung", "cardiac_silhouette", "mediastinum")


def _flatten() -> Dict[str, Tuple[str, str, Optional[str]]]:
    """id -> (sistem, grup, subgrup). Induk lapang paru/siluet/mediastinum dipetakan ke grup masing-masing."""
    out: Dict[str, Tuple[str, str, Optional[str]]] = {}
    for system, groups in THORAX_ANATOMY_TAXONOMY.items():
        if isinstance(groups, list):
            for tid in groups:
                out[tid] = (system, system, None)
            continue
        for group, members in groups.items():
            if isinstance(members, dict):
                for parent, kids in members.items():
                    out[parent] = (system, group, None)
                    for k in kids:
                        out[k] = (system, group, parent)
            else:
                for tid in members:
                    out[tid] = (system, group, None)
        # induk yang bukan daun daftar tetapi nama grup (siluet jantung, mediastinum)
        for g in ("cardiac_silhouette", "mediastinum"):
            if g in groups:
                out[g] = (system, g, None)
    return out


_STRUCT = _flatten()

TAXA: Dict[str, dict] = {}
for _id, _li, _en, _side, _geom, _tier, _prior, _alias in _ROWS:
    _sys, _grp, _par = _STRUCT[_id]
    _col = GROUP_COLOR[_grp]
    TAXA[_id] = {
        "taxon": _id, "label": _en, "label_en": _en, "label_id": _li, "system": _sys, "group": _grp, "parent": _par, "side": _side,
        "geom": _geom, "tier": _tier, "prior": _prior, "aliases": _alias,
        "color": _col[0] if _side == "R" else _col[1] if _side == "L" else _col[2],
    }

# Kesesuaian: setiap id taksonomi harus punya baris registri (dan sebaliknya) - gagal keras saat impor bila tidak.
_missing = set(_STRUCT) - set(TAXA)
_extra = set(TAXA) - set(_STRUCT)
assert not _missing and not _extra, f"registri taksonomi tidak sinkron: kurang={sorted(_missing)} lebih={sorted(_extra)}"

MIRROR: Dict[str, str] = {}
for _id, _t in TAXA.items():
    if _t["side"] in ("R", "L") and ("right" in _id or "left" in _id):
        _cand = _id.replace("right", "\0").replace("left", "right").replace("\0", "left")
        if _cand in TAXA:
            MIRROR[_id] = _cand
# tanpa cermin (asimetris): lobus tengah, lingula, fisura horizontal, SVC, apeks jantung, gelembung lambung, tepi atrium/ventrikel
ZONE_IDS = tuple(i for i, t in TAXA.items() if t["group"] == "zones")


def taxon_info(tid: str) -> Optional[dict]:
    return TAXA.get(tid)


def all_ids() -> List[str]:
    return list(TAXA)


def zone_id(kind: str, side: str) -> str:
    """kind: apex|upper|middle|lower ; side: R|L -> id zona."""
    return f"{'apex' if kind == 'apex' else kind + '_zone'}_{'right' if side == 'R' else 'left'}"


# ---------------------------------------------------------------- resolusi label model -> id baku
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[_\-/()\[\],.:;]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_INDEX: Dict[str, str] = {}
for _id, _t in TAXA.items():
    for _k in (_id, _t["label"], _t["label_id"], *_t["aliases"]):
        _INDEX.setdefault(_norm(_k), _id)

_RIGHT = re.compile(r"\b(kanan|right|dextra|dekstra|dex|rt)\b")
_LEFT = re.compile(r"\b(kiri|left|sinistra|sin|lt)\b")


def side_of_text(text: str) -> Optional[str]:
    """'R' / 'L' bila teks menyebut tepat satu sisi pasien; None bila tidak ada atau menyebut keduanya."""
    t = _norm(text)
    r, l = bool(_RIGHT.search(t)), bool(_LEFT.search(t))
    return "R" if r and not l else "L" if l and not r else None


# Keluarga berpasangan: (regex, id kanan, id kiri). Urutan penting: yang spesifik lebih dulu, 'paru' paling akhir.
_SIDED = [
    (r"kostofrenik|costophrenic|\bcp angle", "right_costophrenic_angle", "left_costophrenic_angle"),
    (r"kardiofrenik|cardiophrenic", "right_cardiophrenic_angle", "left_cardiophrenic_angle"),
    (r"hilus|hilum|hilar", "right_hilum", "left_hilum"),
    (r"hemidiafragma|hemidiaphragm|diafragma|diaphragm", "right_hemidiaphragm", "left_hemidiaphragm"),
    (r"klavikula|clavicle|clavicula", "right_clavicle", "left_clavicle"),
    (r"skapula|scapula", "right_scapula", "left_scapula"),
    (r"bronkus|bronchus|bronchi", "right_main_bronchus", "left_main_bronchus"),
    (r"fisura oblik|fissura oblik|oblique fissure|major fissure|fisura mayor", "oblique_fissure_right", "oblique_fissure_left"),
    (r"lobus atas|upper lobe|lobus superior", "right_upper_lobe", "left_upper_lobe"),
    (r"lobus bawah|lower lobe|lobus inferior", "right_lower_lobe", "left_lower_lobe"),
    (r"lobus tengah|middle lobe|lobus medius", "right_middle_lobe", None),
    (r"lingula", None, "left_lingula"),
    (r"fisura horizontal|horizontal fissure|minor fissure|fisura minor", "horizontal_fissure", None),
    (r"apeks paru|apex paru|apikal|\bapeks\b|\bapex\b|lung apex", "apex_right", "apex_left"),
    (r"zona atas|upper zone|lapang atas|zona superior", "upper_zone_right", "upper_zone_left"),
    (r"zona tengah|middle zone|mid zone|lapang tengah", "middle_zone_right", "middle_zone_left"),
    (r"zona bawah|lower zone|lapang bawah|zona basal|basal", "lower_zone_right", "lower_zone_left"),
]
_LUNG_WORDS = {"paru", "lung", "lungs", "pulmo", "lapang paru", "lung field", "lung fields", "paru paru"}
# Tanpa sisi: (regex, id). Dicek SEBELUM keluarga berpasangan karena sebagian memuat kata kanan/kiri.
_SINGLE = [
    (r"tepi atrium kanan|right atrium|atrium kanan", "right_atrium_border"),
    (r"tepi ventrikel kiri|left ventricle|ventrikel kiri", "left_ventricle_border"),
    (r"apeks jantung|apex cordis|apex jantung|cardiac apex|apex of (the )?heart", "apex_cordis"),
    (r"knob aorta|aortic knob|arkus aorta|aortic arch|aorta knob", "aortic_knob"),
    (r"aorta asenden|ascending aorta", "ascending_aorta"),
    (r"aorta desenden|descending aorta|aorta torakalis", "descending_aorta"),
    (r"vena kava superior|vena cava superior|superior vena cava|\bsvc\b", "superior_vena_cava"),
    (r"arteri pulmonalis|pulmonary artery|pulmonary trunk|truncus pulmonalis|segmen pulmonal", "main_pulmonary_artery"),
    (r"mediastinum superior|superior mediastinum", "superior_mediastinum"),
    (r"mediastinum anterior|anterior mediastinum", "anterior_mediastinum"),
    (r"mediastinum posterior|posterior mediastinum", "posterior_mediastinum"),
    (r"intervertebr|diskus|\bdisc\b|ruang antar", "intervertebral_spaces"),
    (r"vertebra|tulang belakang|\bspine\b|kolumna|columna", "thoracic_vertebrae_T1_T12"),
    (r"iga anterior|rib anterior|anterior rib|kosta anterior", "ribs_anterior_1_to_6"),
    (r"\biga\b|\bribs?\b|kosta", "ribs_posterior_1_to_12"),
    (r"sternum|tulang dada", "sternum"),
    (r"siluet jantung|cardiac silhouette|heart shadow|bayangan jantung|jantung|\bheart\b|\bcor\b|kardiak|kardiomegali|cardiomegaly", "cardiac_silhouette"),
    (r"mediastinum", "mediastinum"),
    (r"trakea|trachea|windpipe", "trachea"),
    (r"karina|carina", "carina"),
    (r"payudara|breast|mamma", "breast_shadow"),
    (r"gelembung gas lambung|gastric|lambung|stomach|magenblase", "gastric_air_bubble"),
    (r"subkutan|subcutaneous|subkutis|jaringan lunak|soft tissue", "subcutaneous_tissue"),
]


def resolve_taxon(text: str, side_hint: Optional[str] = None) -> Optional[str]:
    """Label bebas (id baku, Indonesia, Inggris, atau alias lama) -> id taksonomi; None bila di luar taksonomi.

    `side_hint` ('R'/'L', dari posisi geometri) hanya dipakai bila teks tidak menyebut sisi atau menyebut keduanya."""
    n = _norm(text)
    if not n:
        return None
    if n in _INDEX:
        return _INDEX[n]
    for rx, tid in _SINGLE:
        if re.search(rx, n):
            return tid
    side = side_of_text(n) or side_hint
    for rx, rid, lid in _SIDED:
        if re.search(rx, n):
            if rid and not lid:
                return rid
            if lid and not rid:
                return lid
            return rid if side == "R" else lid if side == "L" else None
    # lapang paru utuh: hanya bila sisa kata (tanpa kata sisi) benar-benar hanya 'paru' - agar 'pembuluh paru' dsb. tidak terbaca paru
    rest = re.sub(r"\b(kanan|right|dextra|dekstra|kiri|left|sinistra|pasien|patient|utuh|seluruh|whole|the)\b", " ", n)
    if re.sub(r"\s+", " ", rest).strip() in _LUNG_WORDS:
        return "right_lung" if side == "R" else "left_lung" if side == "L" else None
    return None


def mirror_id(tid: str) -> Optional[str]:
    return MIRROR.get(tid)


def label_of(tid: str) -> str:
    t = TAXA.get(tid)
    return t["label"] if t else tid


# ---------------------------------------------------------------- blok prompt
_GEOM_NOTE = {"polygon": "polygon", "line": "line", "box": "box", "point": "point/small box"}


def taxonomy_prompt_block() -> str:
    """List of canonical ids per system/group for the prompt. Lung zones are deliberately not requested (derived from the lung outline)."""
    lines = ["THORAX ANATOMY TAXONOMY (Thorax_Anatomy_Taxonomy). The \"id\" of every object in 'structures' MUST be one of the ids below, "
             "exactly as written (lowercase, underscores). Ids outside the list are discarded. Format: id (name) [shape]."]
    for system, groups in THORAX_ANATOMY_TAXONOMY.items():
        lines.append(f"- {SYSTEM_LABEL[system]}:")
        if isinstance(groups, list):
            lines.append("    " + "; ".join(f"{i} ({TAXA[i]['label']}) [{_GEOM_NOTE[TAXA[i]['geom']]}]" for i in groups))
            continue
        for group, members in groups.items():
            if group == "zones":
                continue
            ids: List[str] = []
            if isinstance(members, dict):
                for parent, kids in members.items():
                    ids += [parent] + kids
            else:
                ids = list(members)
                if group in ("cardiac_silhouette", "mediastinum") and group not in ids:
                    ids = [group] + ids
            lines.append(f"    {GROUP_LABEL.get(group, group)}: " + "; ".join(
                f"{i} ({TAXA[i]['label']}) [{_GEOM_NOTE[TAXA[i]['geom']]}]" for i in ids))
    lines.append("- Lung zones (apex_/upper_zone_/middle_zone_/lower_zone_ right/left): you need NOT output them; the system derives them "
                 "from the lung outline. Still use these zone ids in a lesion's 'lokasi_anatomi'.")
    return "\n".join(lines)


def tier_ids(tier: int) -> List[str]:
    return [i for i, t in TAXA.items() if t["tier"] == tier and t["group"] != "zones"]
