"""Lintasan kedua (grounding pass): menambal temuan yang disebut di teks tetapi tidak punya kotak, dan mengukur CTR.

Masalah yang diperbaiki:
1. Lintasan utama sering menulis temuan di 'diagnosis'/'summary' tetapi 'anomalies' kosong atau hanya berisi temuan di sisi yang salah.
2. Ukuran jantung tidak pernah dihitung. Model hanya menulis "tidak membesar" tanpa dasar, dan di mode Lesi tidak ada siluet jantung.

Cara kerja:
- `find_ungrounded` mencari temuan abnormal pada diagnosis yang tidak punya objek lesi (jenis temuan dan sisi harus cocok).
- `build_grounding_prompt` membuat permintaan sempit: 4 landmark CTR, kotak kedua paru, dan kotak hanya untuk temuan yang kurang.
- `compute_ctr` menghitung CTR dari landmark itu di kode (bukan ditebak model). Landmark digeser ke tepi gradien terdekat pada citra
  (`snap_landmarks`) agar pengukuran bertumpu pada piksel.
- `ctr_anomaly` membuat lesi 'Cardiomegaly (CTR x.xx)' bila CTR >= 0.50 dan model belum melaporkannya.
Semua kegagalan di sini tidak boleh menggagalkan pemindaian: pemanggil cukup memakai hasil lintasan utama.
"""
import base64
import io
import re
from typing import Any, Dict, List, Optional, Tuple

from .common import _as_text, _num
from .geo_utils import box_area, intersect_box
from .json_repair import _iter_json_objects, _try_load
from .text_extract import _strip_reasoning, extract_text
from .normalize import normalize_result
from .thorax_anatomy_taxonomy import side_of_text

GROUNDING_MARK = "GROUNDING PASS"

CTR_NORMAL_MAX = 0.50          # PA: CTR > 0.50 = kardiomegali
CTR_MIN_SANE, CTR_MAX_SANE = 0.25, 0.90

# jenis temuan -> regex. Dipakai untuk mencocokkan teks diagnosis dengan label/deskripsi lesi.
FINDING_GROUPS: Dict[str, "re.Pattern"] = {
    "consolidation": re.compile(r"(konsolidasi|consolidation|airspace|pneumonia|pneumonitis|infiltrat)", re.I),
    "opacity": re.compile(r"(opasitas|opacity|opacities|haziness|hazy|densit)", re.I),
    "effusion": re.compile(r"(efusi|effusion|hidrotoraks|hydrothorax|meniscus|blunt|costophrenic|kostofrenikus)", re.I),
    "mass_nodule": re.compile(r"(massa|\bmass\b|nodul|nodule|tumor|neoplasm|malignan)", re.I),
    "hilar": re.compile(r"(hil(?:us|um|ar)|limfadenopati|lymphaden)", re.I),
    "atelectasis": re.compile(r"(atelektasis|atelectasis|kolaps|collapse|volume loss)", re.I),
    "pneumothorax": re.compile(r"(pneumotoraks|pneumothorax)", re.I),
    "cardiomegaly": re.compile(r"(kardiomegali|cardiomegaly|cardiac enlargement|pembesaran jantung|enlarged heart)", re.I),
    "cavity": re.compile(r"(kavitas|cavit)", re.I),
    "fibrosis": re.compile(r"(fibrosis|interstitial|interstisial|reticul)", re.I),
    "edema": re.compile(r"(edema paru|pulmonary (?:o)?edema|kerley|butterfly)", re.I),
}

# Kelompok yang saling melengkapi: opasitas basal di diagnosis boleh dipenuhi lesi 'konsolidasi' atau 'efusi' pada sisi yang sama.
_EQUIV = {
    "opacity": ("opacity", "consolidation", "effusion", "atelectasis", "fibrosis", "mass_nodule"),
    "consolidation": ("consolidation", "opacity"),
    "effusion": ("effusion", "opacity"),
    "atelectasis": ("atelectasis", "opacity", "consolidation"),
    "mass_nodule": ("mass_nodule", "opacity", "hilar"),
    "hilar": ("hilar", "mass_nodule", "opacity"),
}

_NEG_BEFORE = re.compile(r"(tanpa|tidak (?:ada|tampak|terlihat)|bukan|\bno\b|without|absent|negative|not seen|no evidence of|rule out|r/o)[^.;,\n]{0,28}$", re.I)
_NAMES = {
    "consolidation": "consolidation", "opacity": "opacity", "effusion": "pleural effusion / blunted costophrenic angle",
    "mass_nodule": "mass or nodule", "hilar": "hilar prominence or enlargement", "atelectasis": "atelectasis",
    "pneumothorax": "pneumothorax", "cardiomegaly": "cardiomegaly", "cavity": "cavity",
    "fibrosis": "interstitial or fibrotic change", "edema": "pulmonary oedema pattern",
}


def _sides_in(text: str) -> set:
    """Sisi yang disebut pada teks: subset {'R','L'}. 'bilateral' = keduanya."""
    s = set()
    t = text or ""
    if re.search(r"\b(bilateral|kedua|both)\b", t, re.I):
        return {"R", "L"}
    for m in re.finditer(r"\b(right|kanan|left|kiri)\b", t, re.I):
        s.add("R" if m.group(1).lower() in ("right", "kanan") else "L")
    return s


def _lesion_text(a: dict) -> str:
    return f"{a.get('label', '')} {a.get('description', '')}"


def find_ungrounded(result: dict, anomalies: list) -> List[dict]:
    """Temuan abnormal yang disebut di diagnosis utama tetapi tidak punya lesi (jenis cocok dan sisi cocok).
    Mengembalikan [{'group','side'(R/L/None),'text'}]. Temuan yang dinegasikan ('no pneumothorax') diabaikan."""
    diag = str(result.get("diagnosis") or "")
    out: List[dict] = []
    if not diag:
        return out
    kept = [a for a in anomalies or [] if a.get("box") or a.get("polygon")]
    # hanya klausa pertama sebelum "no acute ..." / "tanpa ..." yang bersifat positif
    for name, rx in FINDING_GROUPS.items():
        m = None
        for mm in rx.finditer(diag):
            if _NEG_BEFORE.search(diag[max(0, mm.start() - 40):mm.start()]):
                continue
            m = mm
            break
        if not m:
            continue
        # sisi: ambil sisi yang disebut dekat kata temuan (jendela 60 karakter ke kiri/kanan), kalau tidak ada pakai seluruh diagnosis
        win = diag[max(0, m.start() - 60):m.end() + 40]
        sides = _sides_in(win) or _sides_in(diag)
        side = next(iter(sides)) if len(sides) == 1 else None
        want = _EQUIV.get(name, (name,))
        ok = False
        for a in kept:
            at = _lesion_text(a)
            if not any(FINDING_GROUPS[g].search(at) for g in want):
                continue
            a_sides = _sides_in(at)
            if not a_sides:
                loc = " ".join(a.get("lokasi_anatomi") or [])
                a_sides = {"R"} if "right" in loc else {"L"} if "left" in loc else set()
            if side is None or not a_sides or side in a_sides:
                ok = True
                break
        if not ok:
            word = {"R": "right", "L": "left"}.get(side or "", "")
            out.append({"group": name, "side": side, "text": (word + " " + _NAMES[name]).strip()})
    # satu temuan sering cocok dengan beberapa kelompok ("basal opacity ... effusion ... atelectasis"): gabungkan yang sama sisi dan saling setara
    merged: List[dict] = []
    for m in out:
        host = next((h for h in merged if h["side"] == m["side"] and (m["group"] in _EQUIV.get(h["group"], ()) or h["group"] in _EQUIV.get(m["group"], ()))), None)
        if host:
            host["text"] += f" (possibly {m['text'].replace(host['side'] and {'R': 'right', 'L': 'left'}[host['side']] or '', '').strip()})"
        else:
            merged.append(m)
    return merged


def build_grounding_prompt(result: dict, missing: List[dict], img_wh=None, fov=None) -> str:
    size = f"{img_wh[0]} x {img_wh[1]} pixels" if img_wh else "as sent"
    fov_note = (f"The picture area (non-black) lies at x {fov[0]:.2f}-{fov[2]:.2f}, y {fov[1]:.2f}-{fov[3]:.2f}. " if fov else "")
    diag = str(result.get("diagnosis") or "")[:300]
    summ = str(result.get("summary") or "")[:900]
    first = "; ".join(f"{a.get('label')}" for a in (result.get("anomalies") or [])[:8]) or "none"
    todo = "\n".join(f"- {m['text']}" for m in missing) if missing else "- (none from the first pass; still re-check the areas listed below)"
    return (
        f"{GROUNDING_MARK} (localisation and measurement only). You are looking at ONE frontal chest radiograph of {size}. {fov_note}"
        "A first reading produced this text; it is NOT proof, verify everything on the pixels:\n"
        f"DIAGNOSIS: {diag}\nSUMMARY: {summ}\nLESIONS ALREADY BOXED: {first}\n\n"
        "TASK A - HEART SIZE (mandatory). Choose ONE horizontal level (level_y) where the heart is widest. At that level give four x positions: "
        "right_border_x and left_border_x = the outer edges of the heart shadow (patient's right = image LEFT), and right_inner_x and left_inner_x = the "
        "INNER edges of the rib cage (inner chest wall) at the widest point of the thorax. Also heart top_y and bottom_y. Do not guess 'normal': "
        "place the lines on the visible borders; the code computes the cardiothoracic ratio.\n"
        "TASK B - LUNG FIELDS. Give a box for the aerated right lung and left lung (no shoulders, chest wall, or area below the diaphragm).\n"
        "TASK C - FINDINGS TO LOCALISE. Give a TIGHT box (and polygon when the edge is clear) for each of these, on the correct side "
        "(patient's right = image LEFT; patient's left = image RIGHT):\n"
        f"{todo}\n"
        "Also re-check and box any visible abnormality in: both lower zones and costophrenic angles, both hila, the left and right heart border, "
        "the apices. Each finding: {\"label\": \"... with side and zone\", \"side\": \"right|left|bilateral|midline\", \"zone\": \"apex|upper|middle|lower|hilar|costophrenic\", "
        "\"severity_score\": 0.0-1.0, \"description\": \"...\", \"box\": {xmin,ymin,xmax,ymax}, \"polygon\": [[x,y],...]}. "
        "An uncertain or indeterminate finding still gets a box with a LOW severity_score; do not omit it. Never box ribs, clavicles, soft tissue, "
        "ECG leads or devices.\n"
        "COORDINATES: decimals 0.0-1.0 normalised to the WHOLE image (x right, y down, origin top-left); never pixels or percentages.\n"
        "Reply with ONE raw JSON object only, no markdown:\n"
        "{\"heart\": {\"level_y\": 0.0, \"right_border_x\": 0.0, \"left_border_x\": 0.0, \"top_y\": 0.0, \"bottom_y\": 0.0}, "
        "\"thorax\": {\"right_inner_x\": 0.0, \"left_inner_x\": 0.0}, "
        "\"lungs\": {\"right\": {\"xmin\": 0.0, \"ymin\": 0.0, \"xmax\": 0.0, \"ymax\": 0.0}, \"left\": {\"xmin\": 0.0, \"ymin\": 0.0, \"xmax\": 0.0, \"ymax\": 0.0}}, "
        "\"findings\": []}"
    )


def _num01(v) -> Optional[float]:
    x = _num(v)
    if x is None:
        return None
    if x > 1.5:                      # model menjawab persen atau 0..1000
        x = x / 100.0 if x <= 100 else x / 1000.0
    return x if 0.0 <= x <= 1.0 else None


def _box01(b) -> Optional[dict]:
    if not isinstance(b, dict):
        return None
    vals = [_num01(b.get(k)) for k in ("xmin", "ymin", "xmax", "ymax")]
    if any(v is None for v in vals):
        return None
    x0, y0, x1, y1 = vals
    x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
    if x1 - x0 < 0.05 or y1 - y0 < 0.05:
        return None
    return {"xmin": x0, "ymin": y0, "xmax": x1, "ymax": y1}


def _load_json(raw_content) -> Optional[dict]:
    """JSON terbesar dari keluaran model. parse_with_mode khusus skema diagnosis (menolak objek tanpa kunci diagnosis), jadi tidak dipakai di sini."""
    raw = extract_text(raw_content)
    if not raw or not raw.strip():
        return None
    text = _strip_reasoning(raw) or raw
    if text.lstrip()[:1] == "{":
        obj, _m = _try_load(text)
        if isinstance(obj, dict) and obj:
            return obj
    best, best_len = None, 0
    for cand in _iter_json_objects(text):
        o, _m = _try_load(cand)
        if isinstance(o, dict) and len(cand) > best_len:
            best, best_len = o, len(cand)
    return best


def parse_grounding(raw_content, img_wh=None, model_lower: str = "", fov=None) -> Optional[dict]:
    """Keluaran model lintasan kedua -> {'heart':{}, 'thorax':{}, 'lungs':{'right','left'}, 'findings':[lesi ternormalisasi]}. None bila tak terbaca."""
    obj = _load_json(raw_content)
    if not isinstance(obj, dict) or not obj:
        return None
    for k in ("result", "data", "output"):
        if isinstance(obj.get(k), dict) and not any(x in obj for x in ("heart", "findings", "lungs")):
            obj = obj[k]
            break
    heart = obj.get("heart") if isinstance(obj.get("heart"), dict) else {}
    thorax = obj.get("thorax") if isinstance(obj.get("thorax"), dict) else {}
    lungs_raw = obj.get("lungs") if isinstance(obj.get("lungs"), dict) else {}
    lungs = {}
    for side in ("right", "left"):
        b = _box01(lungs_raw.get(side) or lungs_raw.get(f"{side}_lung"))
        if b:
            lungs[side] = b
    findings = []
    fl = obj.get("findings") or obj.get("anomalies") or []
    if isinstance(fl, dict):
        fl = [fl]
    if isinstance(fl, list) and fl:
        wrapped = normalize_result({"diagnosis": "x", "anomalies": fl}, img_wh, model_lower, fov)
        for a in wrapped.get("anomalies", []):
            if a.get("box"):
                a["source"] = "grounding_pass"
                findings.append(a)
    return {
        "heart": {k: _num01(heart.get(k)) for k in ("level_y", "right_border_x", "left_border_x", "top_y", "bottom_y")},
        "thorax": {k: _num01(thorax.get(k)) for k in ("right_inner_x", "left_inner_x")},
        "lungs": _sane_lungs(lungs, fov),
        "findings": findings,
    }


def _sane_lungs(lungs: dict, fov=None) -> dict:
    """Kotak paru dipakai sebagai bukti letak (sisi/zona), jadi harus masuk akal: kanan di kiri gambar, kiri di kanan gambar."""
    x0, x1 = (fov[0], fov[2]) if fov else (0.0, 1.0)
    mid = (x0 + x1) / 2
    out = {}
    r, l = lungs.get("right"), lungs.get("left")
    if r and (r["xmin"] + r["xmax"]) / 2 < mid and 0.10 <= r["xmax"] - r["xmin"] <= 0.55 and r["ymax"] - r["ymin"] >= 0.2:
        out["right"] = r
    if l and (l["xmin"] + l["xmax"]) / 2 > mid and 0.10 <= l["xmax"] - l["xmin"] <= 0.55 and l["ymax"] - l["ymin"] >= 0.2:
        out["left"] = l
    return out


# --------------------------------------------------------------------------------------------- CTR

def _gray_array(base64_jpeg: str):
    try:
        import numpy as np
        from PIL import Image, ImageOps
        from scipy import ndimage as ndi  # noqa: F401
    except Exception:
        return None
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(base64.b64decode(base64_jpeg)))).convert("L")
        a = np.asarray(im).astype(float) / 255.0
        return a
    except Exception:
        return None


def snap_landmarks(a, lm: Dict[str, float]) -> Tuple[Dict[str, float], bool]:
    """Geser tiap landmark x ke tepi gradien terkuat terdekat (jendela +-4% lebar) pada pita baris di sekitar level_y.
    Tanda gradien dicek: tepi kanan jantung gelap->terang, kiri jantung terang->gelap, dinding dada dalam kanan terang->gelap, kiri gelap->terang.
    Bila tidak ada tepi jelas, nilai dari model dipertahankan."""
    try:
        import numpy as np
        from scipy import ndimage as ndi
    except Exception:
        return dict(lm), False
    if a is None:
        return dict(lm), False
    h, w = a.shape
    y = lm["level_y"]
    r0, r1 = max(0, int((y - 0.025) * h)), min(h, int((y + 0.025) * h) + 1)
    if r1 - r0 < 2:
        return dict(lm), False
    core = a[int(.1 * h):int(.9 * h), int(.1 * w):int(.9 * w)]
    lo, hi = np.percentile(core, 2), np.percentile(core, 98)
    n = np.clip((a - lo) / max(1e-6, hi - lo), 0, 1)
    row = ndi.gaussian_filter1d(n[r0:r1].mean(axis=0), sigma=max(1.0, 0.006 * w))
    grad = np.gradient(row)
    sign = {"right_border_x": +1, "left_border_x": -1, "right_inner_x": -1, "left_inner_x": +1}
    out, moved = dict(lm), False
    win = 0.04
    for k, sg in sign.items():
        x = lm[k]
        lo_i, hi_i = max(1, int((x - win) * w)), min(w - 2, int((x + win) * w))
        if hi_i <= lo_i:
            continue
        seg = sg * grad[lo_i:hi_i + 1]
        j = int(np.argmax(seg))
        if seg[j] >= 0.003:
            nx = (lo_i + j) / w
            if abs(nx - x) > 1e-4:
                moved = True
            out[k] = nx
    return out, moved


def compute_ctr(grounded: dict, image_gray=None) -> Optional[dict]:
    """CTR = lebar jantung / lebar dalam toraks pada level yang sama. Mengembalikan None bila landmark tidak masuk akal."""
    if not grounded:
        return None
    h, t = grounded.get("heart") or {}, grounded.get("thorax") or {}
    lm = {"level_y": h.get("level_y"), "right_border_x": h.get("right_border_x"), "left_border_x": h.get("left_border_x"),
          "right_inner_x": t.get("right_inner_x"), "left_inner_x": t.get("left_inner_x")}
    if any(v is None for v in lm.values()):
        return None
    snapped, moved = snap_landmarks(image_gray, lm)

    def calc(d):
        hw = d["left_border_x"] - d["right_border_x"]
        tw = d["left_inner_x"] - d["right_inner_x"]
        ok = (d["right_inner_x"] < d["right_border_x"] < d["left_border_x"] < d["left_inner_x"] and hw > 0.12 and tw > 0.35)
        return (hw / tw if ok and tw > 0 else None), hw, tw

    ctr_s, hw_s, tw_s = calc(snapped)
    ctr_m, hw_m, tw_m = calc(lm)
    # snapping hanya dipakai bila hasilnya masuk akal dan tidak melompat jauh dari ukuran model
    if ctr_s is not None and CTR_MIN_SANE <= ctr_s <= CTR_MAX_SANE and (ctr_m is None or abs(ctr_s - ctr_m) <= 0.15):
        ctr, hw, tw, used, src = ctr_s, hw_s, tw_s, snapped, "landmark + tepi piksel" if moved else "landmark model"
    elif ctr_m is not None and CTR_MIN_SANE <= ctr_m <= CTR_MAX_SANE:
        ctr, hw, tw, used, src = ctr_m, hw_m, tw_m, lm, "landmark model"
    else:
        return None
    top, bot = h.get("top_y"), h.get("bottom_y")
    if top is None or bot is None or not (0.0 <= top < bot <= 1.0) or (bot - top) < 0.12:
        top, bot = max(0.0, used["level_y"] - 0.14), min(1.0, used["level_y"] + 0.14)
    cat = "normal" if ctr <= CTR_NORMAL_MAX else "kardiomegali"
    return {
        "ctr": round(ctr, 3), "kategori": cat, "sumber": src,
        "lebar_jantung": round(hw, 3), "lebar_toraks": round(tw, 3), "level_y": round(used["level_y"], 3),
        "box_jantung": {"xmin": round(used["right_border_x"], 4), "ymin": round(top, 4),
                        "xmax": round(used["left_border_x"], 4), "ymax": round(bot, 4)},
        "catatan": "CTR dihitung di kode dari landmark; pada citra AP/supine, rotasi, atau inspirasi dangkal nilai dapat terlalu besar.",
    }


def _ctr_score(ctr: float) -> float:
    return 0.30 if ctr < 0.55 else 0.50 if ctr < 0.60 else 0.68 if ctr < 0.65 else 0.82


def has_cardiomegaly_lesion(anomalies: list) -> bool:
    return any(FINDING_GROUPS["cardiomegaly"].search(f"{a.get('label', '')}") for a in anomalies or [])


def ctr_anomaly(info: dict) -> dict:
    ctr = info["ctr"]
    score = _ctr_score(ctr)
    b = info["box_jantung"]
    return {
        "id": "lesion_ctr", "label": f"Cardiomegaly (CTR {ctr:.2f})",
        "severity": "Low" if score < 0.34 else "Moderate" if score < 0.67 else "High",
        "severity_score": score, "severity_score_source": "ctr",
        "description": f"Cardiothoracic ratio {ctr:.2f} (heart width {info['lebar_jantung']:.2f} / internal thoracic width {info['lebar_toraks']:.2f}), above 0.50.",
        "box": dict(b), "lokasi_anatomi": ["cardiac_silhouette"], "source": "ctr_local",
        "pointer": {"targetX": round((b["xmin"] + b["xmax"]) / 2, 4), "targetY": round((b["ymin"] + b["ymax"]) / 2, 4),
                    "labelX": round(min(0.95, b["xmax"] + 0.03), 4), "labelY": round(max(0.05, b["ymin"] - 0.03), 4)},
    }


def apply_ctr(result: dict, anomalies: list, info: Optional[dict]) -> Optional[str]:
    """Tulis hasil pengukuran ke `result` dan tambahkan lesi kardiomegali bila perlu. Mengembalikan catatan log."""
    if not info:
        return None
    result["pengukuran_lokal"] = {"ctr": info}
    summ = str(result.get("summary") or "")
    if info["kategori"] == "kardiomegali":
        had = has_cardiomegaly_lesion(anomalies)
        if not had:
            anomalies.append(ctr_anomaly(info))
        diag = str(result.get("diagnosis") or "")
        if not FINDING_GROUPS["cardiomegaly"].search(diag):
            result["diagnosis"] = f"{diag.rstrip('. ')}, with cardiomegaly (CTR {info['ctr']:.2f})"
        result["summary"] = (f"Cardiac size: the measured cardiothoracic ratio is {info['ctr']:.2f} (above 0.50), consistent with cardiomegaly; "
                             "this overrides any statement below that the heart is not enlarged. ") + summ
        if re.search(r"(not (?:clearly )?enlarged|within normal limits|normal (?:cardiac|heart)|tidak membesar)", summ, re.I):
            result["diagnosis_perlu_verifikasi"] = True
        return f"CTR {info['ctr']:.2f} > 0.50: cardiomegaly " + ("already reported by the model" if had else "added as a lesion with a box on the heart")
    if FINDING_GROUPS["cardiomegaly"].search(str(result.get("diagnosis") or "")):
        result["catatan_ctr"] = f"The model reported cardiomegaly but the measured CTR is {info['ctr']:.2f} (<= 0.50); please verify manually."
        result["diagnosis_perlu_verifikasi"] = True
    return f"CTR {info['ctr']:.2f} within normal limit"


# --------------------------------------------------------------------------------------------- penggabungan

def _iou(a: dict, b: dict) -> float:
    inter = intersect_box(a, b)
    if not inter:
        return 0.0
    ia = box_area(inter)
    return ia / max(1e-9, box_area(a) + box_area(b) - ia)


def _group_of(a: dict) -> Optional[str]:
    t = _lesion_text(a)
    for name, rx in FINDING_GROUPS.items():
        if rx.search(t):
            return name
    return None


def merge_grounded(anomalies: list, grounded: Optional[dict], missing: List[dict]) -> List[str]:
    """Tambahkan lesi dari lintasan kedua yang belum ada. Duplikat = jenis sama dan (IoU > 0.3 atau sisi sama). Mengubah `anomalies` di tempat."""
    notes: List[str] = []
    if not grounded:
        return notes
    for g in grounded.get("findings", []):
        if has_cardiomegaly_lesion([g]):
            continue                                       # kardiomegali ditentukan oleh pengukuran CTR, bukan tebakan
        gname, gsides = _group_of(g), _sides_in(_lesion_text(g))
        dup = False
        for a in anomalies:
            if not (isinstance(a.get("box"), dict) and isinstance(g.get("box"), dict)):
                continue
            same_kind = _group_of(a) == gname or (gname in _EQUIV and _group_of(a) in _EQUIV.get(gname, ()))
            asides = _sides_in(_lesion_text(a))
            if _iou(a["box"], g["box"]) > 0.3 or (same_kind and asides and gsides and asides & gsides and _iou(a["box"], g["box"]) > 0.05):
                dup = True
                break
        if dup:
            continue
        g = dict(g)
        g["id"] = f"lesion_g{len(anomalies) + 1}"
        anomalies.append(g)
        notes.append(f"added from the grounding pass: {str(g.get('label'))[:50]}")
    return notes


def lung_structures(grounded: Optional[dict], heart_box: Optional[dict] = None) -> List[dict]:
    """Struktur bantu (tidak disimpan) untuk refine_anomaly_geometry di mode Lesi: kotak paru dan jantung dari lintasan kedua."""
    out = []
    if not grounded:
        return out
    for side, tid in (("right", "right_lung"), ("left", "left_lung")):
        b = (grounded.get("lungs") or {}).get(side)
        if b:
            out.append({"taxon": tid, "id": tid, "box": dict(b), "derived": True})
    if heart_box:
        out.append({"taxon": "cardiac_silhouette", "id": "cardiac_silhouette", "box": dict(heart_box), "derived": True})
    return out


async def run_grounding_pass(post, model_name: str, base64_image: str, result: dict, anomalies: list, img_wh=None,
                             model_lower: str = "", fov=None, max_tokens: int = 4000) -> Tuple[Optional[dict], List[dict], Optional[str]]:
    """Panggil model sekali lagi dengan tugas sempit. `post(payload)` adalah coroutine yang mengirim ke router dan mengembalikan httpx.Response.
    Mengembalikan (grounded|None, missing, error|None). Tidak pernah melempar."""
    missing = find_ungrounded(result, anomalies)
    missing = [m for m in missing if m["group"] != "cardiomegaly"]
    prompt = build_grounding_prompt(result, missing, img_wh, fov)
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
        ]}],
        "temperature": 0.0, "max_tokens": max_tokens, "stream": False,
    }
    try:
        resp = await post(payload)
        if resp.status_code != 200:
            return None, missing, f"HTTP {resp.status_code}"
        data = resp.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        msg = (choices[0] or {}).get("message") if choices else None
        if msg is None and isinstance(data, dict):
            msg = {"content": data.get("content") or data.get("output_text") or data.get("text")}
        from .text_extract import extract_message_text
        grounded = parse_grounding(extract_message_text(msg or {}), img_wh, model_lower, fov)
        if grounded is None:
            return None, missing, "response not readable as JSON"
        return grounded, missing, None
    except Exception as e:  # noqa: BLE001
        return None, missing, str(e)[:160]
