"""Fungsi geometri 2D kecil (koordinat ternormalisasi 0..1) untuk koreksi anatomi/lesi. Tanpa dependensi luar."""
import math
from typing import List, Optional, Sequence, Tuple

Pt = Sequence[float]


def poly_area(poly) -> float:
    n = len(poly or [])
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def bbox_of(poly) -> dict:
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return {"xmin": min(xs), "ymin": min(ys), "xmax": max(xs), "ymax": max(ys)}


def box_area(b) -> float:
    return max(0.0, b["xmax"] - b["xmin"]) * max(0.0, b["ymax"] - b["ymin"]) if isinstance(b, dict) else 0.0


def box_poly(b) -> List[List[float]]:
    return [[b["xmin"], b["ymin"]], [b["xmax"], b["ymin"]], [b["xmax"], b["ymax"]], [b["xmin"], b["ymax"]]]


def centroid(poly) -> Tuple[float, float]:
    """Titik berat poligon (berbobot luas); jatuh ke rata-rata titik bila luasnya ~0."""
    a2 = cx = cy = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        c = x1 * y2 - x2 * y1
        a2 += c
        cx += (x1 + x2) * c
        cy += (y1 + y2) * c
    if abs(a2) < 1e-9:
        return sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n
    return cx / (3 * a2), cy / (3 * a2)


def point_in_poly(x: float, y: float, poly) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def point_in_box(x: float, y: float, b, tol: float = 0.0) -> bool:
    return b["xmin"] - tol <= x <= b["xmax"] + tol and b["ymin"] - tol <= y <= b["ymax"] + tol


def nearest_on_segment(px, py, ax, ay, bx, by) -> Tuple[float, float]:
    dx, dy = bx - ax, by - ay
    d2 = dx * dx + dy * dy
    t = 0.0 if d2 < 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / d2))
    return ax + t * dx, ay + t * dy


def snap_into_poly(x: float, y: float, poly) -> Tuple[float, float]:
    """Titik di dalam poligon tetap; titik di luar dipindah ke titik terdekat pada tepi poligon."""
    if point_in_poly(x, y, poly):
        return x, y
    best, bd = (x, y), 1e9
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        qx, qy = nearest_on_segment(x, y, ax, ay, bx, by)
        d = math.hypot(qx - x, qy - y)
        if d < bd:
            bd, best = d, (qx, qy)
    return best


def clip_poly_y(poly, y0: float, y1: float) -> List[List[float]]:
    """Potong poligon pada pita horizontal y0 <= y <= y1 (Sutherland-Hodgman terhadap dua setengah-bidang)."""
    def clip(pts, keep, cross):
        out = []
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            ka, kb = keep(a), keep(b)
            if ka:
                out.append(a)
            if ka != kb:
                out.append(cross(a, b))
        return out

    def at_y(yv):
        return lambda a, b: [a[0] + (b[0] - a[0]) * (yv - a[1]) / ((b[1] - a[1]) or 1e-12), yv]

    pts = [list(p) for p in poly]
    pts = clip(pts, lambda p: p[1] >= y0, at_y(y0)) if pts else pts
    pts = clip(pts, lambda p: p[1] <= y1, at_y(y1)) if pts else pts
    return pts if len(pts) >= 3 else []


def clamp_poly_x(poly, xmin: Optional[float] = None, xmax: Optional[float] = None):
    out = []
    for p in poly:
        x = p[0]
        if xmin is not None:
            x = max(xmin, x)
        if xmax is not None:
            x = min(xmax, x)
        out.append([x, p[1]])
    return out


def overlap_ratio(poly, region_poly) -> float:
    """Perkiraan porsi (0..1) titik-titik poligon (vertex + titik tengah sisi) yang jatuh di dalam region_poly."""
    pts = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        pts += [a, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]]
    if not pts:
        return 0.0
    return sum(1 for p in pts if point_in_poly(p[0], p[1], region_poly)) / len(pts)


def clip_poly_box(poly, b):
    """Potong poligon dengan kotak {xmin,ymin,xmax,ymax} (Sutherland-Hodgman, empat setengah-bidang). [] bila hasilnya < 3 titik."""
    def clip(pts, keep, cross):
        out = []
        for i in range(len(pts)):
            a, c = pts[i], pts[(i + 1) % len(pts)]
            ka, kc = keep(a), keep(c)
            if ka:
                out.append(a)
            if ka != kc:
                out.append(cross(a, c))
        return out

    def at_x(xv):
        return lambda a, c: [xv, a[1] + (c[1] - a[1]) * (xv - a[0]) / ((c[0] - a[0]) or 1e-12)]

    def at_y(yv):
        return lambda a, c: [a[0] + (c[0] - a[0]) * (yv - a[1]) / ((c[1] - a[1]) or 1e-12), yv]

    pts = [list(p) for p in poly or []]
    for keep, cross in (
        (lambda p: p[0] >= b["xmin"], at_x(b["xmin"])), (lambda p: p[0] <= b["xmax"], at_x(b["xmax"])),
        (lambda p: p[1] >= b["ymin"], at_y(b["ymin"])), (lambda p: p[1] <= b["ymax"], at_y(b["ymax"])),
    ):
        if not pts:
            break
        pts = clip(pts, keep, cross)
    return pts if len(pts) >= 3 else []


def intersect_box(a, b):
    """Irisan dua kotak, atau None bila tidak beririsan."""
    r = {"xmin": max(a["xmin"], b["xmin"]), "ymin": max(a["ymin"], b["ymin"]),
         "xmax": min(a["xmax"], b["xmax"]), "ymax": min(a["ymax"], b["ymax"])}
    return r if r["xmax"] > r["xmin"] and r["ymax"] > r["ymin"] else None


def shrink_box_to_area(b, max_area: float, cx: Optional[float] = None, cy: Optional[float] = None):
    """Kecilkan kotak (rasio sisi tetap) di sekitar titik (cx, cy) sampai luasnya <= max_area; hasil tetap di dalam kotak asal."""
    ar = box_area(b)
    if ar <= max_area or ar <= 0:
        return dict(b)
    s = math.sqrt(max_area / ar)
    w, h = (b["xmax"] - b["xmin"]) * s, (b["ymax"] - b["ymin"]) * s
    cx = (b["xmin"] + b["xmax"]) / 2 if cx is None else cx
    cy = (b["ymin"] + b["ymax"]) / 2 if cy is None else cy
    x0 = min(max(cx - w / 2, b["xmin"]), b["xmax"] - w)
    y0 = min(max(cy - h / 2, b["ymin"]), b["ymax"] - h)
    return {"xmin": x0, "ymin": y0, "xmax": x0 + w, "ymax": y0 + h}
