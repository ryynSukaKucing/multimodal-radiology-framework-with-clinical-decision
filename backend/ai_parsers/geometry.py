from .common import _as_text, _num
from .thorax_anatomy_taxonomy import TAXA, resolve_taxon


# Keluarga model yang konvensinya skala 0..1000 (Gemini box_2d, GLM, Qwen-VL). Selain itu dianggap piksel
# citra yang DIKIRIM (lihat prepare_ai_image) bila muat, kalau tidak 0..1000.
_COORD_1000_FAMILIES = ('gemini', 'glm', 'qwen')


def _scale_box(x0, y0, x1, y1, mx, img_wh, model_lower, force_1000=False):
    """Ubah box non-normalisasi menjadi 0..1. Urutan keputusan:
    1) box_2d (gaya Gemini) atau keluarga 0..1000 -> bagi 1000 (selama <= 1000)
    2) <= 100 -> persen
    3) muat di dimensi citra kirim -> piksel
    4) <= 1000 -> 0..1000
    Cabang piksel TIDAK lagi didahulukan untuk keluarga 0..1000, sehingga y tidak lagi dibagi 1700."""
    ml = (model_lower or '').lower()
    prefer_1000 = force_1000 or any(f in ml for f in _COORD_1000_FAMILIES)
    fits_px = bool(img_wh) and x1 <= img_wh[0] * 1.02 and y1 <= img_wh[1] * 1.02 and x0 <= img_wh[0] and y0 <= img_wh[1]
    if prefer_1000 and mx <= 1000:
        return x0 / 1000, y0 / 1000, x1 / 1000, y1 / 1000
    if mx <= 100:
        return x0 / 100, y0 / 100, x1 / 100, y1 / 100
    if fits_px and mx > 100:
        return x0 / img_wh[0], y0 / img_wh[1], x1 / img_wh[0], y1 / img_wh[1]
    if mx <= 1000:
        return x0 / 1000, y0 / 1000, x1 / 1000, y1 / 1000
    return None, None, None, None


def _norm_box(item: dict, img_wh=None, model_lower: str = ''):
    """Kembalikan box {xmin,ymin,xmax,ymax} ternormalisasi 0..1 atau None."""
    raw, gemini_order = None, False
    for k in ('box', 'bbox', 'bounding_box', 'boundingbox', 'bbox_2d', 'box_2d', 'region'):
        if item.get(k) not in (None, '', [], {}):
            raw = item.get(k)
            gemini_order = k == 'box_2d'
            break
    vals = None
    if isinstance(raw, dict):
        def pick(*names):
            for nm in names:
                if nm in raw and _num(raw[nm]) is not None:
                    return _num(raw[nm])
            return None
        x0, y0 = pick('xmin', 'x_min', 'x1', 'left', 'x'), pick('ymin', 'y_min', 'y1', 'top', 'y')
        x1, y1 = pick('xmax', 'x_max', 'x2', 'right'), pick('ymax', 'y_max', 'y2', 'bottom')
        if x1 is None and x0 is not None and pick('w', 'width') is not None:
            x1 = x0 + pick('w', 'width')
        if y1 is None and y0 is not None and pick('h', 'height') is not None:
            y1 = y0 + pick('h', 'height')
        vals = [x0, y0, x1, y1]
    elif isinstance(raw, (list, tuple)) and len(raw) == 4:
        v = [_num(x) for x in raw]
        vals = [v[1], v[0], v[3], v[2]] if gemini_order else v
    if not vals or any(x is None for x in vals):
        return None
    x0, y0, x1, y1 = vals
    mx = max(abs(x0), abs(y0), abs(x1), abs(y1))
    if mx > 1.5:
        x0, y0, x1, y1 = _scale_box(x0, y0, x1, y1, mx, img_wh, model_lower, gemini_order)
        if x0 is None:
            return None
    return {'xmin': x0, 'ymin': y0, 'xmax': x1, 'ymax': y1}


_POLY_KEYS = ('polygon', 'segmentation', 'contour', 'mask_polygon', 'polygon_points', 'outline', 'mask')


def _norm_points(raw, img_wh=None, model_lower: str = '', min_n: int = 3):
    """Ubah titik kontur dari model (list [x,y], list objek {x,y}, atau list datar COCO) menjadi
    [[x,y],...] ternormalisasi 0..1. Mengembalikan [] bila tidak valid."""
    if isinstance(raw, dict):
        for k in ('points', 'xy', 'coordinates', 'polygon', 'contour'):
            if raw.get(k):
                raw = raw[k]
                break
    if not isinstance(raw, (list, tuple)) or not raw:
        return []
    if len(raw) == 1 and isinstance(raw[0], (list, tuple)) and raw[0] and not isinstance(raw[0][0], (list, tuple, dict)):
        raw = raw[0]                                  # COCO: [[x1,y1,x2,y2,...]]
    pts = []
    if all(_num(v) is not None for v in raw) and len(raw) % 2 == 0 and len(raw) >= 2 * min_n:
        pts = [(_num(raw[i]), _num(raw[i + 1])) for i in range(0, len(raw), 2)]   # list datar
    else:
        for p in raw:
            if isinstance(p, dict):
                x, y = _num(p.get('x')), _num(p.get('y'))
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                x, y = _num(p[0]), _num(p[1])
            else:
                continue
            if x is not None and y is not None:
                pts.append((x, y))
    if len(pts) < min_n:
        return []
    mxx, mxy = max(abs(p[0]) for p in pts), max(abs(p[1]) for p in pts)
    mx = max(mxx, mxy)
    ml = (model_lower or '').lower()
    if mx <= 1.5:
        sx = sy = 1.0
    elif any(f in ml for f in _COORD_1000_FAMILIES) and mx <= 1000:
        sx = sy = 1000.0
    elif mx <= 100:
        sx = sy = 100.0
    elif img_wh and mxx <= img_wh[0] * 1.02 and mxy <= img_wh[1] * 1.02:
        sx, sy = float(img_wh[0]), float(img_wh[1])
    elif mx <= 1000:
        sx = sy = 1000.0
    else:
        return []
    return [[round(min(1.0, max(0.0, x / sx)), 4), round(min(1.0, max(0.0, y / sy)), 4)] for x, y in pts]


def _poly_of(item: dict, img_wh=None, model_lower: str = ''):
    for k in _POLY_KEYS:
        if item.get(k) not in (None, '', [], {}):
            pts = _norm_points(item.get(k), img_wh, model_lower)
            if pts:
                return pts
    return []


def _box_from_poly(poly):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return {'xmin': min(xs), 'ymin': min(ys), 'xmax': max(xs), 'ymax': max(ys)}


_LINE_KEYS = ('polyline', 'line', 'centerline', 'curve', 'path', 'garis')
MAX_STRUCTURES = 60


def _line_of(item: dict, img_wh=None, model_lower: str = ''):
    for k in _LINE_KEYS:
        if item.get(k) not in (None, '', [], {}):
            pts = _norm_points(item.get(k), img_wh, model_lower, min_n=2)
            if pts:
                return pts
    return []


def _pad_box(b, m=0.012):
    """Garis/titik sangat tipis: beri ketebalan minimal agar tidak dibuang sebagai box kosong."""
    if (b['xmax'] - b['xmin']) < m:
        c = (b['xmax'] + b['xmin']) / 2
        b['xmin'], b['xmax'] = max(0.0, c - m / 2), min(1.0, c + m / 2)
    if (b['ymax'] - b['ymin']) < m:
        c = (b['ymax'] + b['ymin']) / 2
        b['ymin'], b['ymax'] = max(0.0, c - m / 2), min(1.0, c + m / 2)
    return b


def _center_of(item: dict):
    b = item.get('box')
    if isinstance(b, dict):
        return (b['xmin'] + b['xmax']) / 2, (b['ymin'] + b['ymax']) / 2
    return None


def normalize_structures(raw, img_wh=None, model_lower: str = '', fov=None, report=None) -> list:
    """Struktur anatomi dari model -> daftar baku Thorax_Anatomy_Taxonomy, koordinat 0..1.

    Tiap objek diberi id baku (`id` == `taxon`), nama Indonesia, sistem/grup, bentuk, warna. Label di luar taksonomi dibuang
    (dicatat di `report`). Sisi kiri/kanan yang tidak disebut atau ambigu diputuskan dari posisi pada citra (PA/AP: kanan pasien
    = kiri gambar). Dua objek dengan id sama digabung: yang bergeometri lebih lengkap dipertahankan."""
    if isinstance(raw, dict):
        raw = [dict(v, label=v.get('label') or k) if isinstance(v, dict) else {'label': k} for k, v in raw.items()]
    fx0, fx1 = (fov[0], fov[2]) if fov else (0.0, 1.0)
    best = {}
    order = []
    for i, s in enumerate(raw if isinstance(raw, list) else [], start=1):
        if not isinstance(s, dict):
            continue                                   # teks tanpa koordinat tidak berguna untuk lapisan visual
        names = [_as_text(s.get(k)) for k in ('id', 'taxon', 'label', 'name', 'structure', 'nama') if s.get(k)]
        poly = _poly_of(s, img_wh, model_lower)
        line = _line_of(s, img_wh, model_lower)
        box = _norm_box(s, img_wh, model_lower)
        if not box:
            src = poly or line
            if src:
                box = _box_from_poly(src)
        if not (box or poly or line):
            continue
        cx = (box['xmin'] + box['xmax']) / 2 if box else None
        hint = None
        if cx is not None:
            rel = (cx - fx0) / max(1e-6, fx1 - fx0)
            hint = 'R' if rel < 0.46 else 'L' if rel > 0.54 else None
        tid = next((t for t in (resolve_taxon(n, hint) for n in names) if t), None)
        if not tid:
            if report is not None and names:
                report.append(f"structure outside the taxonomy dropped: {names[-1][:40]}")
            continue
        t = TAXA[tid]
        item = {'id': tid, 'taxon': tid, 'label': t['label'], 'label_en': t['label_en'], 'system': t['system'],
                'group': t['group'], 'side': t['side'], 'geom': t['geom'], 'tier': t['tier'], 'color': t['color'],
                'description': _as_text(s.get('description') or s.get('deskripsi') or s.get('status') or s.get('keterangan'))[:200]}
        model_label = _as_text(s.get('label') or s.get('name') or s.get('nama'))
        if model_label and model_label.lower() != t['label'].lower() and model_label.lower() != tid:
            item['label_model'] = model_label[:60]
        if poly:
            item['polygon'] = poly
        if line:
            item['polyline'] = line
        if box:
            item['box'] = _pad_box(dict(box)) if (t['geom'] in ('line', 'point')) else box
        score = (2 if poly else 0) + (1 if line else 0) + (1 if box else 0)
        if tid not in best:
            order.append(tid)
            best[tid] = (score, item)
        elif score > best[tid][0]:
            best[tid] = (score, item)
        elif report is not None:
            report.append(f"duplicate {tid} ignored")
    out = [best[k][1] for k in order]
    return out[:MAX_STRUCTURES]


def _clamp01(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v != v:
        return None
    return min(1.0, max(0.0, v))


def _clean_points(pts, min_n, max_n=40):
    out = []
    for p in pts or []:
        try:
            x, y = _clamp01(p[0]), _clamp01(p[1])
        except (TypeError, IndexError, KeyError):
            continue
        if x is None or y is None:
            continue
        out.append([round(x, 4), round(y, 4)])
    return out[:max_n] if len(out) >= min_n else []


def sanitize_anomaly_geometry(anomalies):
    """Validasi geometri dari LLM: clamp 0..1, buang box/polygon/centerline yang tidak valid."""
    for a in anomalies or []:
        b = a.get("box")
        if isinstance(b, dict):
            x0, x1 = _clamp01(b.get("xmin")), _clamp01(b.get("xmax"))
            y0, y1 = _clamp01(b.get("ymin")), _clamp01(b.get("ymax"))
            if None in (x0, x1, y0, y1):
                a.pop("box", None)
            else:
                x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
                if (x1 - x0) < 0.01 or (y1 - y0) < 0.01:
                    a.pop("box", None)
                else:
                    a["box"] = {"xmin": x0, "ymin": y0, "xmax": x1, "ymax": y1}
        a["polygon"] = _clean_points(a.get("polygon"), 3)
        if a["polygon"] and isinstance(a.get("box"), dict):
            # kontur harus sejalan dengan kotaknya: pusat kontur di dalam kotak (+toleransi) dan luas kotak kontur tidak jauh melebihi kotak
            pb, bb = _box_from_poly(a["polygon"]), a["box"]
            pcx, pcy = (pb["xmin"] + pb["xmax"]) / 2, (pb["ymin"] + pb["ymax"]) / 2
            tol = 0.03
            inside = bb["xmin"] - tol <= pcx <= bb["xmax"] + tol and bb["ymin"] - tol <= pcy <= bb["ymax"] + tol
            parea = (pb["xmax"] - pb["xmin"]) * (pb["ymax"] - pb["ymin"])
            barea = (bb["xmax"] - bb["xmin"]) * (bb["ymax"] - bb["ymin"])
            if not inside or parea > 2.5 * max(barea, 1e-9):
                a["polygon"] = []
        a["centerline"] = _clean_points(a.get("centerline"), 2)
        kps = []
        for k in a.get("keypoints") or []:
            try:
                x, y = _clamp01(k.get("x")), _clamp01(k.get("y"))
            except AttributeError:
                continue
            if x is not None and y is not None:
                kps.append({"name": str(k.get("name", ""))[:40], "x": round(x, 4), "y": round(y, 4)})
        a["keypoints"] = kps[:10]
        for key in ("polygon", "centerline", "keypoints"):
            if not a[key]:
                a.pop(key)
    return anomalies


def sanitize_structures(structures):
    """Validasi struktur anatomi: clamp 0..1, buang box terlalu kecil, polygon/garis tidak valid."""
    kept = []
    for st in structures or []:
        thin = st.get("geom") in ("line", "point")
        mn = 0.008 if thin else 0.02
        b = st.get("box")
        if isinstance(b, dict):
            x0, x1 = _clamp01(b.get("xmin")), _clamp01(b.get("xmax"))
            y0, y1 = _clamp01(b.get("ymin")), _clamp01(b.get("ymax"))
            if None in (x0, x1, y0, y1):
                st.pop("box", None)
            else:
                x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
                if (x1 - x0) < mn or (y1 - y0) < mn:
                    st.pop("box", None)
                else:
                    st["box"] = {"xmin": x0, "ymin": y0, "xmax": x1, "ymax": y1}
        else:
            st.pop("box", None)
        poly = _clean_points(st.get("polygon"), 3, 60)
        if poly:
            st["polygon"] = poly
            if not st.get("box"):
                st["box"] = _box_from_poly(poly)
        else:
            st.pop("polygon", None)
        line = _clean_points(st.get("polyline"), 2, 40)
        if line:
            st["polyline"] = line
            if not st.get("box"):
                st["box"] = _pad_box(_box_from_poly(line))
        else:
            st.pop("polyline", None)
        if st.get("box") or st.get("polygon") or st.get("polyline"):
            kept.append(st)
    return kept
