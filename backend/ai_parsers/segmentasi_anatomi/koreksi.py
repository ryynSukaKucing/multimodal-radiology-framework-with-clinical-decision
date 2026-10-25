"""Post-model corrections for ANATOMY based on Thorax_Anatomy_Taxonomy.

Urutan di `reconcile_structures`: (1) label -> id baku, (2) sisi kiri/kanan (orientasi global + pasangan), (3) lapang pandang citra,
(4) kewajaran posisi tiap struktur, (5) hierarki paru > lobus/zona dan paru tidak melewati garis tengah, (6) zona paru diturunkan dari
kontur paru. Semua koreksi dicatat sebagai kalimat untuk log pemindaian; tidak ada koordinat yang dikarang selain zona turunan,
yang ditandai `derived: true`.
"""
from typing import Dict, List, Optional, Tuple

from ..geo_utils import (bbox_of, box_poly, centroid, clamp_poly_x, clip_poly_y, point_in_box, poly_area)
from ..thorax_anatomy_taxonomy import MIRROR, TAXA, label_of, resolve_taxon, zone_id

FOV_NONE = (0.0, 0.0, 1.0, 1.0)
PRIOR_MARGIN = 0.20          # jendela posisi taksonomi diperlebar (0.12 -> 0.20): LLM umum tidak presisi, jangan buang struktur sah
MIDLINE_IDS = ("trachea", "carina", "thoracic_vertebrae_T1_T12", "sternum")
ZONE_BANDS = {"apex": (0.0, 0.14), "upper": (0.0, 0.34), "middle": (0.34, 0.67), "lower": (0.67, 1.0)}


def _fov(fov) -> Tuple[float, float, float, float]:
    return tuple(fov) if fov and len(fov) == 4 else FOV_NONE


def apply_taxon(st: dict, tid: str) -> None:
    """Pasang identitas taksonomi (id, nama, sistem, warna, ...) ke objek struktur."""
    t = TAXA[tid]
    st.update({"id": tid, "taxon": tid, "label": t["label"], "label_en": t["label_en"], "system": t["system"], "group": t["group"],
               "side": t["side"], "geom": t["geom"], "tier": t["tier"], "color": t["color"]})


def _drop(lst: list, item: dict) -> None:
    """Hapus berdasarkan identitas objek (list.remove memakai kesamaan nilai, bisa menghapus objek lain yang kembar)."""
    for i, x in enumerate(lst):
        if x is item:
            del lst[i]
            return


def _has(lst: list, item: dict) -> bool:
    return any(x is item for x in lst)


def _ensure_taxon(st: dict) -> Optional[str]:
    """Objek lama (belum bertaksonomi, mis. dari riwayat atau uji) dipetakan lewat label-nya."""
    tid = st.get("taxon")
    if tid in TAXA:
        return tid
    for k in ("id", "label", "name"):
        tid = resolve_taxon(str(st.get(k) or ""))
        if tid:
            apply_taxon(st, tid)
            return tid
    return None


def _center(st: dict) -> Optional[Tuple[float, float]]:
    b = st.get("box")
    if isinstance(b, dict):
        return (b["xmin"] + b["xmax"]) / 2, (b["ymin"] + b["ymax"]) / 2
    for k in ("polygon", "polyline"):
        if st.get(k):
            bb = bbox_of(st[k])
            return (bb["xmin"] + bb["xmax"]) / 2, (bb["ymin"] + bb["ymax"]) / 2
    return None


def _rel(c: Tuple[float, float], fov) -> Tuple[float, float]:
    x0, y0, x1, y1 = _fov(fov)
    return (c[0] - x0) / max(1e-6, x1 - x0), (c[1] - y0) / max(1e-6, y1 - y0)


def midline_x(structures: list, fov=None) -> Tuple[float, bool]:
    """(x garis tengah dalam koordinat citra, dari_landmark). Landmark: trakea/karina/vertebra/sternum; selain itu tengah lapang pandang."""
    xs = []
    for s in structures:
        if s.get("taxon") in MIDLINE_IDS:
            c = _center(s)
            if c and 0.35 <= _rel(c, fov)[0] <= 0.65:
                xs.append(c[0])
    x0, _, x1, _ = _fov(fov)
    if xs:
        xs.sort()
        return xs[len(xs) // 2], True
    return (x0 + x1) / 2, False


def _observed_side(st: dict, mid: float, fov, tol: float = 0.04) -> Optional[str]:
    c = _center(st)
    if not c:
        return None
    x0, _, x1, _ = _fov(fov)
    w = max(1e-6, x1 - x0)
    d = (c[0] - mid) / w
    return "R" if d < -tol else "L" if d > tol else None      # PA/AP: kanan pasien = sisi KIRI gambar


def fix_laterality(structures: list, fov=None, dropped: Optional[list] = None) -> List[str]:
    """Perbaiki sisi kiri/kanan (dimodifikasi di tempat). Bukti: letak tiap struktur berpasangan terhadap garis tengah.

    Label sisi hanya diubah/dibuang bila garis tengah berasal dari LANDMARK (trakea/karina/vertebra/sternum). Tanpa landmark garis
    tengah hanyalah tengah citra, bukti yang terlalu lemah: struktur yang tampak berlawanan cuma diberi `geometry_warning`
    dan `lateralitas_tidak_pasti`, lalu dicatat. Dengan landmark: bila mayoritas (berbobot) terbalik, seluruh label sisi dibalik
    sekaligus; sisa struktur yang masih berlawanan ditukar dengan pasangannya bila keduanya terbalik, selain itu dibuang.
    `dropped` (opsional) diisi {label, alasan} untuk setiap struktur yang dibuang, agar bisa ditampilkan di UI."""
    notes: List[str] = []
    dropped = dropped if dropped is not None else []
    keep = [s for s in structures if _ensure_taxon(s)]
    if len(keep) != len(structures):
        lost = [s for s in structures if not _ensure_taxon(s)]
        for s in lost:
            dropped.append({"label": str(s.get("label") or s.get("id") or "?"), "alasan": "tidak punya id taksonomi"})
        notes.append(f"{len(lost)} structures without a taxonomy id were dropped ({', '.join(str(x.get('label') or x.get('id') or '?') for x in lost)})")
    structures[:] = keep
    mid, landmark = midline_x(structures, fov)
    tol = 0.04

    def evidence():
        agree = disagree = 0
        for s in structures:
            if s.get("side") not in ("R", "L"):
                continue
            ob = _observed_side(s, mid, fov, tol)
            if ob is None:
                continue
            w = 2 if s.get("tier") == 1 else 1
            if ob == s["side"]:
                agree += w
            else:
                disagree += w
        return agree, disagree

    agree, disagree = evidence()
    if disagree >= 2 and disagree > agree and not landmark:
        for s in structures:
            ob = _observed_side(s, mid, fov, tol)
            if s.get("side") in ("R", "L") and ob is not None and ob != s["side"]:
                s["lateralitas_tidak_pasti"] = True
                s["geometry_warning"] = "Sisi pada label dan posisi struktur berbeda; belum ada landmark garis tengah untuk memastikan."
        notes.append(f"possible left/right reversal ({disagree} of {agree + disagree} evidence weight) NOT applied: no midline landmark "
                     "(trachea/carina/spine/sternum); labels left as-is, please verify orientation manually")
        return notes
    if disagree >= 2 and disagree > agree:
        flipped, lost_pairs = 0, []
        for s in list(structures):
            if s.get("side") not in ("R", "L"):
                continue
            m = MIRROR.get(s["taxon"])
            if m:
                apply_taxon(s, m)
                flipped += 1
            else:
                _drop(structures, s)
                lost_pairs.append(s.get("label", ""))
                dropped.append({"label": str(s.get("label", "")), "alasan": "tidak punya pasangan saat orientasi kiri/kanan dibalik"})
        notes.append(f"left/right orientation reversed ({disagree} of {agree + disagree} evidence weight): {flipped} side labels flipped"
                     + (f", {len(lost_pairs)} without a counterpart dropped ({', '.join(lost_pairs)})" if lost_pairs else "")
                     + " [patient right = image left]")
        # struktur yang awalnya cocok kini berlawanan; evaluasi ulang di bawah
    by_id: Dict[str, dict] = {s["taxon"]: s for s in structures}
    for s in list(structures):
        if not _has(structures, s) or s.get("side") not in ("R", "L"):
            continue
        ob = _observed_side(s, mid, fov, tol)
        if ob is None or ob == s["side"]:
            continue
        if not landmark:
            s["lateralitas_tidak_pasti"] = True
            s["geometry_warning"] = "Sisi pada label dan posisi struktur berbeda; belum ada landmark garis tengah untuk memastikan."
            notes.append(f"{s.get('label')}: side vs position mismatch kept as-is (no midline landmark), flagged for manual check")
            continue
        m = MIRROR.get(s["taxon"])
        other = by_id.get(m) if m else None
        if other and _has(structures, other) and _observed_side(other, mid, fov, tol) == s["side"]:
            a, b = s["taxon"], other["taxon"]
            apply_taxon(s, b)
            apply_taxon(other, a)
            by_id[b], by_id[a] = s, other
            notes.append(f"{label_of(a)} and {label_of(b)} swapped (image positions were reversed)")
        elif s.get("tier") == 1:
            s["lateralitas_tidak_pasti"] = True
            s["geometry_warning"] = "Struktur utama berada di sisi berlawanan dengan labelnya; mohon verifikasi."
            notes.append(f"{s.get('label')}: lies on the opposite side of its label; tier-1 structure kept with a warning")
        else:
            _drop(structures, s)
            why = f"lies on the patient's {'left' if ob == 'R' else 'right'} side, which does not match its label"
            dropped.append({"label": str(s.get("label", "")), "alasan": why})
            notes.append(f"{s.get('label')} dropped: {why}")
    return notes


def _clamp_struct_to_fov(st: dict, fov) -> None:
    x0, y0, x1, y1 = _fov(fov)
    cl = lambda p: [min(x1, max(x0, p[0])), min(y1, max(y0, p[1]))]
    for k in ("polygon", "polyline"):
        if st.get(k):
            st[k] = [cl(p) for p in st[k]]
    b = st.get("box")
    if isinstance(b, dict):
        st["box"] = {"xmin": max(x0, b["xmin"]), "ymin": max(y0, b["ymin"]), "xmax": min(x1, b["xmax"]), "ymax": min(y1, b["ymax"])}


def _plausible(st: dict, fov) -> Optional[str]:
    """Alasan penolakan bila pusat struktur jauh di luar jendela posisi taksonominya; None bila wajar."""
    t = TAXA.get(st.get("taxon"))
    c = _center(st)
    if not t or not c:
        return None
    cx, cy = _rel(c, fov)
    x0, x1, y0, y1, _, _ = t["prior"]
    m = PRIOR_MARGIN
    if cx < x0 - m or cx > x1 + m or cy < y0 - m or cy > y1 + m:
        return f"{t['label']} dropped: position ({cx:.2f}, {cy:.2f}) is outside the plausible location for this structure"
    return None


def _oversize(st: dict, fov) -> bool:
    t = TAXA.get(st.get("taxon"))
    b = st.get("box")
    if not t or not isinstance(b, dict):
        return False
    x0, _, x1, _ = _fov(fov)
    w = (b["xmax"] - b["xmin"]) / max(1e-6, x1 - x0)
    h = (b["ymax"] - b["ymin"]) / max(1e-6, _fov(fov)[3] - _fov(fov)[1])
    return w > t["prior"][4] * 1.35 or h > t["prior"][5] * 1.35


def _new_item(tid: str, polygon: list, desc: str) -> dict:
    st: dict = {}
    apply_taxon(st, tid)
    st["polygon"] = [[round(p[0], 4), round(p[1], 4)] for p in polygon]
    st["box"] = bbox_of(st["polygon"])
    st["description"] = desc
    st["derived"] = True
    return st


def derive_zones(structures: list) -> List[dict]:
    """Zona paru (apeks/atas/tengah/bawah) sebagai irisan horizontal kontur paru yang SUDAH dideteksi model. Bukan temuan baru."""
    by_id = {s["taxon"]: s for s in structures}
    out = []
    for side, lung_id in (("R", "right_lung"), ("L", "left_lung")):
        lung = by_id.get(lung_id)
        if not lung:
            continue
        poly = lung.get("polygon") or (box_poly(lung["box"]) if isinstance(lung.get("box"), dict) else None)
        if not poly or len(poly) < 3:
            continue
        bb = bbox_of(poly)
        h = bb["ymax"] - bb["ymin"]
        if h < 0.05:
            continue
        for kind, (a, b) in ZONE_BANDS.items():
            zid = zone_id(kind, side)
            if zid in by_id:
                continue
            piece = clip_poly_y(poly, bb["ymin"] + a * h, bb["ymin"] + b * h)
            if piece and poly_area(piece) > 0.0005:
                out.append(_new_item(zid, piece, "zone derived from the lung outline"))
    return out


def reconcile_structures(structures: list, fov=None) -> Tuple[list, List[str]]:
    """Titik masuk koreksi anatomi (kompatibel): (struktur_bersih, catatan). Lihat reconcile_structures_ex untuk daftar yang dibuang."""
    final, notes, _ = reconcile_structures_ex(structures, fov)
    return final, notes


def reconcile_structures_ex(structures: list, fov=None) -> Tuple[list, List[str], List[dict]]:
    """Koreksi anatomi. Mengembalikan (struktur_bersih, catatan, dibuang) dengan dibuang = [{label, alasan}, ...].
    Setiap struktur yang dibuang masuk log DAN daftar `dibuang` (ditampilkan di UI: "Struktur dibuang: ...")."""
    work = [dict(s) for s in structures or []]
    dropped: List[dict] = []
    notes = fix_laterality(work, fov, dropped)
    fx0, fy0, fx1, fy1 = _fov(fov)
    kept = []
    for s in work:
        c = _center(s)
        if c and fov and not (fx0 - 0.03 <= c[0] <= fx1 + 0.03 and fy0 - 0.03 <= c[1] <= fy1 + 0.03):
            notes.append(f"{s['label']} dropped: outside the image field of view (black area)")
            dropped.append({"label": s["label"], "alasan": "di luar lapang pandang citra (area hitam)"})
            continue
        _clamp_struct_to_fov(s, fov)
        why = _plausible(s, fov)
        if why:
            if s.get("tier") == 1:
                # struktur utama (paru, jantung, hilus, mediastinum, trakea, diafragma): beri peringatan, jangan buang diam-diam
                s["geometry_warning"] = "Posisi di luar jendela yang lazim untuk struktur ini; mohon verifikasi."
                notes.append(why.replace(" dropped:", ": kept with a warning,"))
            else:
                notes.append(why)
                dropped.append({"label": s["label"], "alasan": "posisi di luar jendela yang masuk akal untuk struktur ini"})
                continue
        if _oversize(s, fov):
            s["geometry_warning"] = "Size exceeds what is plausible for this structure; please re-check."
            notes.append(f"{s['label']}: size exceeds plausible range")
        kept.append(s)
    by_id = {s["taxon"]: s for s in kept}

    # paru tidak melewati garis tengah
    mid, landmark = midline_x(kept, fov)
    tol = 0.03 if landmark else 0.10
    w = max(1e-6, fx1 - fx0)
    for lid, side in (("right_lung", "R"), ("left_lung", "L")):
        lung = by_id.get(lid)
        if not lung:
            continue
        lim_lo, lim_hi = (None, mid + tol * w) if side == "R" else (mid - tol * w, None)
        changed = False
        if lung.get("polygon"):
            new = clamp_poly_x(lung["polygon"], lim_lo, lim_hi)
            changed = new != lung["polygon"]
            lung["polygon"] = new
            lung["box"] = bbox_of(new)
        elif isinstance(lung.get("box"), dict):
            b = lung["box"]
            nb = dict(b)
            if lim_hi is not None:
                nb["xmax"] = min(b["xmax"], lim_hi)
            if lim_lo is not None:
                nb["xmin"] = max(b["xmin"], lim_lo)
            changed = nb != b
            lung["box"] = nb
        if changed:
            notes.append(f"{lung['label']} clamped so it does not cross the midline")

    # hierarki: lobus & zona harus berada di dalam paru sisinya
    final = []
    for s in kept:
        par = TAXA[s["taxon"]]["parent"]
        lung = by_id.get(par) if par else None
        if not par and TAXA[s["taxon"]]["group"] == "zones":
            lung = by_id.get("right_lung" if s["side"] == "R" else "left_lung")
        if lung and isinstance(lung.get("box"), dict) and s is not lung:
            c = _center(s)
            if c and not point_in_box(c[0], c[1], lung["box"], 0.04):
                notes.append(f"{s['label']} dropped: outside {lung['label']}")
                dropped.append({"label": s["label"], "alasan": f"berada di luar {lung['label']}"})
                continue
        final.append(s)
    zones = derive_zones(final)
    if zones:
        notes.append(f"{len(zones)} lung zones derived from the lung outline (not model detections)")
    final = sorted(final, key=lambda s: (s.get("tier", 3), s.get("taxon", ""))) + zones
    return final, notes, dropped
