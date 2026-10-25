"""Koreksi pasca-model untuk LESI: tautkan tiap lesi ke anatomi (Thorax_Anatomy_Taxonomy) dan samakan teks dengan letak yang tergambar.

Prinsip: teks (sisi, zona) hanya disesuaikan dengan letak kotak bila ada bukti geometri yang KUAT: kontur paru hasil deteksi model
(bukan perkiraan `_prior`) atau garis tengah dari landmark (trakea/karina/vertebra/sternum). Kotak dari LLM umum sendiri tidak
terverifikasi, jadi tanpa bukti kuat teks TIDAK diubah; lesi hanya ditandai `lateralitas_tidak_pasti` + `geometry_warning`.
Setiap perubahan ditandai pada lesinya (`koreksi_lateralitas`, `koreksi_zona`) dan dicatat untuk log.
"""
import re
from typing import List, Optional, Tuple

import copy

from ..geo_utils import (bbox_of, box_area, box_poly, centroid, clip_poly_box, intersect_box, overlap_ratio, point_in_box,
                         point_in_poly, poly_area, shrink_box_to_area, snap_into_poly)
from ..segmentasi_anatomi.koreksi import midline_x
from ..thorax_anatomy_taxonomy import TAXA, label_of, resolve_taxon, side_of_text, zone_id

_PARENKIM = re.compile(r"(konsolidasi|infiltrat|opasitas|nodul|massa|kavitas|atelektasis|consolidation|infiltrate|opacity|nodule|mass|cavit|atelectasis)", re.I)
_DIFFUSE = re.compile(r"(efusi|effusion|milier|miliary|edema|oedema|kardiomegali|cardiomegaly|fibrosis difus|diffuse fibrosis|infiltrat difus|diffuse infiltrate|hiperinflasi|hyperinflation|pneumotoraks|pneumothorax)", re.I)
_BILATERAL = re.compile(r"(bilateral|kedua (?:sisi|paru|lapang)|both|difus|diffuse)", re.I)
_MIDLINE = re.compile(r"(kardiomegali|cardiomegaly|jantung|heart|cardiac|mediastin|trakea|trachea|aort|sternum|vertebra|spine|tulang belakang|karina|carina)", re.I)

_SWAP = {"kanan": "kiri", "kiri": "kanan", "right": "left", "left": "right", "dextra": "sinistra", "dekstra": "sinistra",
         "sinistra": "dextra"}
_SWAP_RX = re.compile(r"\b(kanan|kiri|right|left|dextra|dekstra|sinistra)\b", re.I)

_ZONE_TXT = (
    ("apex", re.compile(r"(apeks|apex|apikal|apical)", re.I)),
    ("upper", re.compile(r"(zona atas|lapang atas|upper zone|upper lobe|lobus atas|zona superior)", re.I)),
    ("middle", re.compile(r"(zona tengah|lapang tengah|middle zone|mid zone|middle lobe|lobus tengah)", re.I)),
    ("lower", re.compile(r"(zona bawah|lapang bawah|lower zone|zona basal|basal|lobus bawah|lower lobe)", re.I)),
)
_ZONE_NAME_ID = {"apex": "apex", "upper": "upper", "middle": "middle", "lower": "lower"}
_ZONE_REWRITE = re.compile(r"\b(?:(zona|lapang)\s+(atas|tengah|bawah|basal)|(upper|middle|lower)\s+zone)\b", re.I)
_ZONE_ID_EN = {"atas": "upper", "tengah": "middle", "bawah": "lower", "basal": "lower"}
_BAND = {"apex": (0.0, 0.14), "upper": (0.0, 0.34), "middle": (0.34, 0.67), "lower": (0.67, 1.0)}
ZONE_TOL = 0.08


def swap_side_words(text: str) -> str:
    """kanan<->kiri (dan right<->left) dengan huruf besar-kecil dipertahankan."""
    def rep(m):
        w = m.group(0)
        r = _SWAP[w.lower()]
        return r.upper() if w.isupper() and len(w) > 1 else (r.capitalize() if w[0].isupper() else r)
    return _SWAP_RX.sub(rep, text or "")


def _poly_area(poly) -> float:        # nama lama dipertahankan
    return poly_area(poly)


def _box_area(b) -> float:
    return box_area(b)


def _side_of(text: str):
    s = side_of_text(text)
    return {"R": "kanan", "L": "kiri"}.get(s)


def _clip_points(poly, b):
    return [[min(b["xmax"], max(b["xmin"], x)), min(b["ymax"], max(b["ymin"], y))] for x, y in poly]


def _zone_of_text(text: str) -> Optional[str]:
    for k, rx in _ZONE_TXT:
        if rx.search(text or ""):
            return k
    return None


def _lesion_center(a: dict) -> Optional[Tuple[float, float]]:
    if a.get("polygon"):
        return centroid(a["polygon"])
    b = a.get("box")
    return ((b["xmin"] + b["xmax"]) / 2, (b["ymin"] + b["ymax"]) / 2) if isinstance(b, dict) else None


def _lung_shape(lung: dict):
    if lung.get("polygon"):
        return lung["polygon"]
    return box_poly(lung["box"]) if isinstance(lung.get("box"), dict) else None


def _locate(c, lungs: dict, mid: float, fovw: float, landmark: bool):
    """(sisi 'R'/'L'/None, lung_id/None, t_vertikal 0..1 dalam paru/None, sumber)."""
    for side, lid in (("R", "right_lung"), ("L", "left_lung")):
        lung = lungs.get(lid)
        shp = _lung_shape(lung) if lung else None
        if shp and (point_in_poly(c[0], c[1], shp) or (not lung.get("polygon") and point_in_box(c[0], c[1], lung["box"], 0.01))):
            if lung.get("_prior"):
                # kotak tetap perkiraan (bukan deteksi): cukup untuk membatasi lesi, TIDAK cukup sebagai bukti sisi/zona
                return side, lid, None, "perkiraan"
            bb = bbox_of(shp)
            h = max(1e-6, bb["ymax"] - bb["ymin"])
            return side, lid, min(1.0, max(0.0, (c[1] - bb["ymin"]) / h)), "kontur paru"
    d = (c[0] - mid) / fovw
    tol = 0.10
    if abs(d) > tol:
        return ("R" if d < 0 else "L"), None, None, "garis tengah" if landmark else "tengah citra"
    return None, None, None, ""



# Batas ukuran/letak lesi (koordinat 0..1). Lesi fokal harus rapat; lesi meluas (efusi, edema, pola difus) boleh lebih besar tetapi tetap di dalam paru.
FOCAL_MAX_LUNG_FRAC = 0.45      # lesi fokal: maks 45% luas kotak paru sisinya
EXTENSIVE_MAX_LUNG_FRAC = 0.85  # lesi meluas: maks 85% luas kotak paru sisinya
MIDLINE_MAX_AREA = 0.12         # lesi mediastinum/hilus tengah: maks 12% luas citra (kardiomegali dikecualikan)
MIN_INSIDE_FRAC = 0.25          # minimal 25% lesi harus berada di dalam paru; kurang dari itu dianggap salah tempat dan dibuang
MIN_SIDE = 0.02
EFFUSION_TOP_FRAC = 0.30        # efusi hanya di bagian basal: tidak boleh mulai di atas 30% tinggi paru
_EXTENSIVE = re.compile(r"(efusi|effusion|milier|miliary|edema|oedema|fibrosis difus|diffuse fibrosis|infiltrat difus|diffuse infiltrate|"
                        r"hiperinflasi|hyperinflation|pneumotoraks|pneumothorax|difus|diffuse|bilateral|reticul|zones|zona-zona|lobar|lobus|\blobe\b|"
                        r"(?:upper|middle|lower|atas|tengah|bawah)\s*(?:and|dan|&|,)\s*(?:upper|middle|lower|atas|tengah|bawah))", re.I)
_EFFUSION = re.compile(r"(efusi|effusion)", re.I)
_CARDIAC = re.compile(r"(kardiomegali|cardiomegaly|jantung|heart|cardiac)", re.I)
_MEDIASTINAL = re.compile(r"(mediastin|trakea|trachea|paratrakeal|paratracheal|aort|karina|carina|sternum|vertebra|spine|tulang belakang)", re.I)
_HILAR = re.compile(r"(hilus|hilum|hilar)", re.I)


def _expand(b: dict, m: float) -> dict:
    return {"xmin": max(0.0, b["xmin"] - m), "ymin": max(0.0, b["ymin"] - m), "xmax": min(1.0, b["xmax"] + m), "ymax": min(1.0, b["ymax"] + m)}


def _prior_lungs(fov) -> dict:
    """Perkiraan kasar lapang paru (longgar) bila model tidak memberi kontur paru, mis. mode Lesi saja."""
    x0, y0, x1, y1 = tuple(fov) if fov and len(fov) == 4 else (0.0, 0.0, 1.0, 1.0)
    w, h = x1 - x0, y1 - y0

    def mk(xa, xb):
        return {"box": {"xmin": x0 + xa * w, "ymin": y0 + 0.06 * h, "xmax": x0 + xb * w, "ymax": y0 + 0.96 * h}, "_prior": True}
    return {"right_lung": mk(0.04, 0.50), "left_lung": mk(0.50, 0.96)}


def _map_poly(poly, ob: dict, nb: dict):
    """Petakan poligon dari kotak lama ke kotak baru (affine), supaya bentuknya tetap utuh saat kotak dikecilkan."""
    ow, oh = max(1e-9, ob["xmax"] - ob["xmin"]), max(1e-9, ob["ymax"] - ob["ymin"])
    sx, sy = (nb["xmax"] - nb["xmin"]) / ow, (nb["ymax"] - nb["ymin"]) / oh
    return [[nb["xmin"] + (x - ob["xmin"]) * sx, nb["ymin"] + (y - ob["ymin"]) * sy] for x, y in poly]


def _split_bilateral(anomalies: list, lungs: dict, mid: float, fovw: float, notes: List[str]) -> list:
    """Satu kotak yang melintasi garis tengah untuk lesi bilateral/difus dipecah menjadi satu kotak per paru (tanpa kotak raksasa di mediastinum)."""
    out = []
    rl, ll = lungs.get("right_lung"), lungs.get("left_lung")
    for a in anomalies:
        b = a.get("box")
        text = f"{a.get('label', '')} {a.get('description', '')}"
        if (rl and ll and isinstance(b, dict) and re.search(r"(bilateral|kedua (?:sisi|paru|lapang)|both)", text, re.I)
                and b["xmin"] < mid - 0.04 * fovw and b["xmax"] > mid + 0.04 * fovw and not _MIDLINE.search(a.get("label", ""))):
            for side, lung, word in (("R", rl, "right lung"), ("L", ll, "left lung")):
                lb = lung["box"] if isinstance(lung.get("box"), dict) else bbox_of(_lung_shape(lung))
                part = intersect_box(b, lb)
                if not part or box_area(part) < MIN_SIDE * MIN_SIDE * 4:
                    continue
                c = copy.deepcopy(a)
                c["box"] = part
                c.pop("polygon", None)                     # kontur lama melintasi dua paru; heatmap memakai oval di dalam kotak baru
                c["id"] = f"{a.get('id', 'lesion')}_{side}"
                if not side_of_text(c.get("label", "")):
                    c["label"] = f"{c.get('label', '')} ({word})"
                out.append(c)
            notes.append(f"{a.get('label')}: one box spanning both lungs was split into one box per lung")
        else:
            out.append(a)
    return out


def _fit_geometry(a: dict, text: str, lung: Optional[dict], side: Optional[str], skip_midline: bool, anat: dict, fov, notes: List[str]) -> bool:
    """Pas-kan kotak/kontur lesi: ke dalam region yang masuk akal, ukuran dibatasi, kontur di dalam kotak. False bila lesi harus dibuang."""
    box = a.get("box")
    if not isinstance(box, dict):
        return True
    label = a.get("label", "")
    poly = a.get("polygon") or None
    ob = dict(box)
    extensive = bool(_EXTENSIVE.search(text))
    cap = None
    region = None

    if skip_midline:
        ref = anat.get("cardiac_silhouette") if _CARDIAC.search(label) else anat.get("mediastinum") if _MEDIASTINAL.search(label) else None
        if ref and isinstance(ref.get("box"), dict):
            region = _expand(ref["box"], 0.04)
        if not _CARDIAC.search(label):
            cap = MIDLINE_MAX_AREA
    elif lung is not None:
        lb = lung["box"] if isinstance(lung.get("box"), dict) else bbox_of(_lung_shape(lung))
        h = lb["ymax"] - lb["ymin"]
        region = dict(lb)
        if _EFFUSION.search(text):
            region = dict(region, ymin=max(region["ymin"], lb["ymin"] + EFFUSION_TOP_FRAC * h))
        cap = (EXTENSIVE_MAX_LUNG_FRAC if extensive else FOCAL_MAX_LUNG_FRAC) * box_area(lb)

    if region is not None:
        inter = intersect_box(box, region)
        # kontur paru dari model kadang kasar/kecil: hanya dipercaya untuk membuang lesi bila kotak paru cukup besar
        strict = lung is not None and not lung.get("_prior") and box_area(region) >= 0.06
        if skip_midline:
            if inter is not None:                          # lesi tengah (jantung/mediastinum) tidak pernah dibuang karena letak
                box = inter
        else:
            if inter is None or (strict and box_area(inter) < MIN_INSIDE_FRAC * box_area(box)) or (not strict and box_area(inter) < 0.05 * box_area(box)):
                notes.append(f"{label}: box lies mostly outside the expected area (lung field / below the diaphragm / wrong region), removed")
                return False
            if box_area(inter) < box_area(box) * 0.999:
                notes.append(f"{label}: box clipped to stay inside the {'lung field' if lung is not None else 'expected region'}")
            box = inter
    if (box["xmax"] - box["xmin"]) < MIN_SIDE or (box["ymax"] - box["ymin"]) < MIN_SIDE:
        notes.append(f"{label}: box too small after correction, removed")
        return False

    if cap is not None and box_area(box) > cap:
        c = centroid(poly) if poly else None
        nb = shrink_box_to_area(box, cap, c[0] if c else None, c[1] if c else None)
        notes.append(f"{label}: box covered {box_area(box):.0%} of the image, tightened to {box_area(nb):.0%}")
        if poly:
            poly = _map_poly(poly, box, nb)
        box = nb
        a["koreksi_ukuran"] = True

    if poly:
        clipped = clip_poly_box(poly, box)
        if not clipped or poly_area(clipped) < 0.25 * max(1e-9, poly_area(poly)):
            poly = None                                    # kontur tidak cocok dengan kotak: pakai kotak saja (heatmap oval di dalam kotak)
            notes.append(f"{label}: outline did not match the box, outline removed (box kept)")
        else:
            poly = [[round(x, 4), round(y, 4)] for x, y in clipped]
            tb = bbox_of(poly)
            pad = 0.004
            box = intersect_box(box, {"xmin": tb["xmin"] - pad, "ymin": tb["ymin"] - pad, "xmax": tb["xmax"] + pad, "ymax": tb["ymax"] + pad}) or box
    a["box"] = {k: round(v, 4) for k, v in box.items()}
    if poly:
        a["polygon"] = poly
    else:
        a.pop("polygon", None)
    if isinstance(a.get("pointer"), dict):
        a["pointer"] = {"targetX": round((box["xmin"] + box["xmax"]) / 2, 4), "targetY": round((box["ymin"] + box["ymax"]) / 2, 4),
                        "labelX": round(min(0.95, box["xmax"] + 0.03), 4), "labelY": round(max(0.05, box["ymin"] - 0.03), 4)}
    return True


def refine_anomaly_geometry(anomalies: list, structures: list, fov=None) -> List[str]:
    """Tautkan lesi ke anatomi, selaraskan sisi/zona teks dengan letak, lalu pas-kan kotak dan kontur lesi:
    di dalam paru sisinya (atau kardiak/mediastinum untuk lesi tengah), ukuran lesi fokal dibatasi, kontur di dalam kotak.
    Lesi yang letaknya salah (mis. di bawah diafragma) ditandai `_drop` dan dibuang oleh pemanggil. `anomalies` diubah di tempat
    (lesi bilateral berkotak tunggal dapat dipecah menjadi dua)."""
    notes: List[str] = []
    lungs, anat = {}, {}
    for s in structures or []:
        tid = s.get("taxon") or resolve_taxon(str(s.get("label") or ""))
        if tid in ("right_lung", "left_lung") and (isinstance(s.get("box"), dict) or s.get("polygon")):
            lungs[tid] = s
        if tid and isinstance(s.get("box"), dict):
            anat[tid] = s
    if not lungs:
        lungs = _prior_lungs(fov)
        notes.append("no lung outline from the model: approximate lung fields were used to bound lesions")
    else:
        for lid, pr in _prior_lungs(fov).items():
            lungs.setdefault(lid, pr)
    mid, landmark = midline_x(structures or [], fov)
    x0, y0, x1, y1 = tuple(fov) if fov and len(fov) == 4 else (0.0, 0.0, 1.0, 1.0)
    fovw = max(1e-6, x1 - x0)

    anomalies[:] = _split_bilateral(anomalies, lungs, mid, fovw, notes)

    for a in anomalies:
        text = f"{a.get('label', '')} {a.get('description', '')}"
        c = _lesion_center(a)
        if c and fov and not (x0 - 0.03 <= c[0] <= x1 + 0.03 and y0 - 0.03 <= c[1] <= y1 + 0.03):
            a.pop("box", None)
            a.pop("polygon", None)
            a["_drop"] = True
            a["geometry_warning"] = "Location is outside the image field of view; location removed."
            notes.append(f"{a.get('label')}: outside the image field of view, removed")
            continue
        obs_side, lung_id, t, src = _locate(c, lungs, mid, fovw, landmark) if c else (None, None, None, "")
        text_side = side_of_text(a.get("label", "")) or side_of_text(a.get("description", ""))
        skip_midline = bool(_MIDLINE.search(a.get("label", "")) and not _HILAR.search(text))
        skip_side = bool(_BILATERAL.search(text) or skip_midline)

        # 1) sisi: teks mengikuti letak HANYA bila bukti kuat (kontur paru nyata, bukan _prior, atau garis tengah dari landmark)
        real_lung = bool(lung_id and not lungs.get(lung_id, {}).get("_prior"))
        strong = real_lung or landmark
        if text_side and obs_side and not skip_side:
            if text_side != obs_side:
                if strong:
                    a["label"] = swap_side_words(a.get("label", ""))
                    a["description"] = swap_side_words(a.get("description", ""))
                    a["koreksi_lateralitas"] = True
                    a["koreksi_lateralitas_dasar"] = "kontur paru" if real_lung else "landmark"
                    notes.append(f"{a['label']}: side in the text was swapped to match the lesion position ({src})")
                    text_side = obs_side
                else:
                    a["lateralitas_tidak_pasti"] = True
                    a["geometry_warning"] = "Sisi pada teks dan posisi kotak berbeda; posisi belum terverifikasi."
                    notes.append(f"{a.get('label')}: side mismatch left as-is (no reliable lung/midline reference)")
            else:
                a["lateralitas_cocok"] = True
        side = obs_side or (text_side if not skip_side else None)

        # 2) zona: teks mengikuti letak (hanya bila kontur paru tersedia dan lesi parenkim fokal)
        zone_obs = None
        if t is not None:
            zone_obs = "upper" if t < 0.34 else "middle" if t < 0.67 else "lower"
            zt = _zone_of_text(text)
            multi_zone = sum(1 for _, rx in _ZONE_TXT if rx.search(text)) > 1 or bool(re.search(r"(upper|middle|lower|atas|tengah|bawah)\s*(?:and|dan|&|,)\s*(upper|middle|lower|atas|tengah|bawah)", text, re.I))
            if zt and not multi_zone and not _DIFFUSE.search(text) and not _BILATERAL.search(text):
                lo, hi = _BAND[zt]
                if t < lo - ZONE_TOL or t > hi + ZONE_TOL:
                    fix = lambda m: (f"{m.group(1)} " + {"upper": "atas", "middle": "tengah", "lower": "bawah"}[zone_obs]) if m.group(1) else f"{zone_obs} zone"
                    new_label = _ZONE_REWRITE.sub(fix, a.get("label", ""), count=1)
                    if new_label != a.get("label"):
                        a["label"] = new_label
                        a["description"] = _ZONE_REWRITE.sub(fix, a.get("description", ""), count=1)
                        a["koreksi_zona"] = True
                        notes.append(f"{a['label']}: zone in the text was adjusted to the lesion's position in the lung")
                    else:
                        a["geometry_warning"] = f"The text states the {_ZONE_NAME_ID[zt]} zone, but the lesion lies in the {_ZONE_NAME_ID[zone_obs]} zone."
                        notes.append(f"{a.get('label')}: stated {_ZONE_NAME_ID[zt]} zone does not match the position ({_ZONE_NAME_ID[zone_obs]} zone)")

        # 3) pas-kan kotak/kontur: dalam paru sisinya, ukuran dibatasi, kontur di dalam kotak
        lung = lungs.get({"R": "right_lung", "L": "left_lung"}.get(side or "")) if side else None
        if lung is not None and a.get("polygon") and lung.get("polygon") and not skip_midline:
            shp = _lung_shape(lung)
            a["polygon"] = [[round(px, 4), round(py, 4)] for px, py in (snap_into_poly(p[0], p[1], shp) for p in a["polygon"])]
        snap = (copy.deepcopy(a.get("box")), copy.deepcopy(a.get("polygon")))
        if not _fit_geometry(a, text, lung, side, skip_midline, anat, fov, notes):
            a["_snap"] = snap
            a.pop("box", None)
            a.pop("polygon", None)
            a["_drop"] = True
            continue

        # 4) tautan anatomi (id taksonomi), dihitung dari letak AKHIR lesi
        c2 = _lesion_center(a)
        if c2:
            o2, l2, t2, s2 = _locate(c2, lungs, mid, fovw, landmark)
            if l2 and not lungs.get(l2, {}).get("_prior"):
                lung_id, t, src = l2, t2, s2
                if t is not None:
                    zone_obs = "upper" if t < 0.34 else "middle" if t < 0.67 else "lower"
        ids: List[str] = []
        if lung_id and not lungs.get(lung_id, {}).get("_prior"):
            ids.append(lung_id)
        if lung_id and zone_obs and side and not lungs.get(lung_id, {}).get("_prior"):
            ids.append(zone_id(zone_obs, side))
            if t is not None and t < 0.14:
                ids.append(zone_id("apex", side))
        for cand in list(a.get("lokasi_anatomi") or []) + [resolve_taxon(a.get("label", ""), side)]:
            if not cand or cand not in TAXA or cand in ids:
                continue
            cs = TAXA[cand]["side"]
            if side and cs in ("R", "L") and cs != side and not skip_side:
                continue                                   # id dari model bersisi lain daripada letak -> buang
            ids.append(cand)
        a["lokasi_anatomi"] = ids
        zone_sides = {zid for zid in ids if TAXA[zid]["group"] == "zones"}
        show = [i for i in ids if not (i in ("right_lung", "left_lung") and any(TAXA[z]["side"] == TAXA[i]["side"] for z in zone_sides))]
        a["lokasi_label"] = ", ".join(label_of(i) for i in show[:3])
        a["lokasi_sumber"] = src or ("model" if ids else "")

        area = max(poly_area(a.get("polygon")), box_area(a.get("box")))
        if area > 0.30 and not _DIFFUSE.search(f"{a.get('label', '')} {a.get('description', '')}"):
            a["geometry_warning"] = "Area too large for a focal lesion; please re-check."
            notes.append(f"{a.get('label')}: area {area:.0%} of the image, probably covers the whole lung")
    # Jaring pengaman: bila SEMUA lesi akan dibuang, jangan tampilkan citra kosong. Kembalikan lesi apa adanya dengan peringatan.
    live = [a for a in anomalies if a.get("box") or a.get("_drop")]
    if live and all(a.get("_drop") and a.get("_snap") and a["_snap"][0] for a in live):
        for a in live:
            a["box"], poly = a["_snap"]
            if poly:
                a["polygon"] = poly
            a.pop("_drop", None)
            a["geometry_warning"] = "Location could not be verified against the lung field; please check it manually."
        notes.append("every lesion failed the location check, so they were kept as reported by the model (flagged for manual check)")
    for a in anomalies:
        a.pop("_snap", None)
    return notes


def align_text_laterality(result: dict, anomalies: list, landmark: bool = False) -> Optional[str]:
    """Catat koreksi sisi pada lesi di `result["catatan_lateralitas"]` (ditampilkan di UI).

    Ringkasan/diagnosis/SOAP TIDAK dibalik otomatis. Pembalikan hanya terjadi bila SEMUA lesi bersisi terbalik, tidak ada yang
    cocok atau tidak pasti, dan garis tengah berasal dari landmark (trakea/vertebra/sternum): saat itu model hampir pasti memakai
    konvensi gambar (bukan pasien) secara konsisten. Selain itu hanya catatan peringatan."""
    flipped = [a for a in anomalies if a.get("koreksi_lateralitas")]
    agree = sum(1 for a in anomalies if a.get("lateralitas_cocok"))
    unsure = sum(1 for a in anomalies if a.get("lateralitas_tidak_pasti"))
    if not flipped and not unsure:
        return None
    if not flipped:
        note = (f"Left/right side on {unsure} lesion(s) does not match the box position, but there is no reliable lung outline or midline "
                "landmark to decide which is right; text was left unchanged. Please verify the side manually.")
        result["catatan_lateralitas"] = note
        return note
    n = len(flipped)
    if agree == 0 and unsure == 0 and landmark:
        for k in ("summary", "diagnosis"):
            if isinstance(result.get(k), str):
                result[k] = swap_side_words(result[k])
        if isinstance(result.get("diagnosis_alternatif"), list):
            result["diagnosis_alternatif"] = [swap_side_words(x) if isinstance(x, str) else x for x in result["diagnosis_alternatif"]]
        if isinstance(result.get("soap"), dict):
            result["soap"] = {k: swap_side_words(v) if isinstance(v, str) else v for k, v in result["soap"].items()}
        note = (f"Left/right side on all {n} lesion(s) was corrected to match its position relative to the midline landmarks "
                "(patient right = image left); summary and diagnosis were adjusted accordingly.")
    else:
        note = (f"Left/right side on {n} of {n + agree + unsure} lesion(s) was corrected to match its position on the image"
                + (f"; {unsure} could not be verified" if unsure else "")
                + ". Summary and diagnosis were NOT changed automatically; please re-check them.")
    result["catatan_lateralitas"] = note
    return note
