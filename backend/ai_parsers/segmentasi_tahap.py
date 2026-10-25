"""Panggilan 2 dari 2 (tombol "Segmentasi"): kontur untuk objek yang SUDAH dideteksi pada panggilan 1.

Panggilan 1 (deteksi objek) hanya menulis kotak + diagnosis, sehingga keluarannya pendek dan kotaknya fokus. Panggilan ini menerima citra yang sama
beserta daftar kotak final dari panggilan 1, lalu hanya meminta kontur (polygon untuk lesi/organ, polyline untuk garis) per id.
Kotak TIDAK diubah di sini: kontur yang keluar dari kotaknya dibuang oleh `sanitize_anomaly_geometry` / dikoreksi `refine_anomaly_geometry`.
"""
import json
from typing import Dict, List, Optional, Tuple

from .geometry import _clean_points, _line_of, _poly_of
from .json_repair import _iter_json_objects, _try_load
from .prompts.geometry_notes import build_image_scale_note
from .segmentasi_anatomi.prompt import PROMPT_SEGMENTASI_ANATOMI
from .segmentasi_lesi.prompt import PROMPT_SEGMENTASI_LESI
from .text_extract import _strip_reasoning, extract_text

SEGMENTATION_MARK = "SEGMENTATION PASS"
MAX_SEG_STRUCTURES = 24          # organ dengan kontur per panggilan (prioritas tier 1 lalu 2)
MAX_SEG_LESIONS = 20
_DROP_BUDGET_NOTE = "Token budget is limited: outlines only for priority 1; priority 2-3 need only a box."


def _r(b: dict) -> dict:
    return {k: round(float(b[k]), 3) for k in ("xmin", "ymin", "xmax", "ymax")}


def pick_lesions(anomalies: list) -> List[dict]:
    """Lesi yang punya kotak valid (hanya ini yang bisa disegmentasi)."""
    out = [a for a in anomalies or [] if isinstance(a.get("box"), dict)]
    return out[:MAX_SEG_LESIONS]


def pick_structures(structures: list) -> List[dict]:
    """Organ yang layak diberi kontur: bukan zona turunan, bentuk polygon/garis, prioritas tier 1 lalu 2."""
    cand = [s for s in structures or []
            if not s.get("derived") and isinstance(s.get("box"), dict) and s.get("geom") in ("polygon", "line")
            and s.get("tier", 3) <= 2]
    cand.sort(key=lambda s: (s.get("tier", 3), s.get("taxon", "")))
    return cand[:MAX_SEG_STRUCTURES]


def build_segmentation_prompt(anomalies: list, structures: list, img_wh=None, fov=None) -> str:
    """Prompt panggilan 2. Berisi aturan kontur (dipakai ulang dari tahap 3 dan 4), ukuran citra, daftar kotak final, dan skema keluaran."""
    les = pick_lesions(anomalies)
    sts = pick_structures(structures)
    parts = [
        f"{SEGMENTATION_MARK} (call 2 of 2). You are given the SAME image and the objects already detected in call 1. "
        "Your only job now is to draw OUTLINES for those objects. Do not detect new objects, do not rename, do not move or resize any box, "
        "and do not write a diagnosis or any prose. Reply with ONE raw JSON object and nothing else (no markdown, no commentary)."
    ]
    if les:
        parts.append(PROMPT_SEGMENTASI_LESI)
    if sts:
        parts.append(PROMPT_SEGMENTASI_ANATOMI.replace(_DROP_BUDGET_NOTE, "").strip())
    parts.append(build_image_scale_note(img_wh, fov).strip())

    lines: List[str] = []
    if les:
        lines.append("LESIONS (each needs \"polygon\" inside its own box; use the id exactly):")
        for a in les:
            lines.append(json.dumps({
                "id": a.get("id"), "label": str(a.get("label", ""))[:80], "box": _r(a["box"]),
                "lokasi_anatomi": a.get("lokasi_anatomi") or [],
            }, ensure_ascii=False))
    if sts:
        lines.append("ANATOMICAL STRUCTURES (shape 'polygon' needs \"polygon\"; shape 'line' needs \"polyline\"; use the id exactly):")
        for s in sts:
            lines.append(json.dumps({
                "id": s.get("taxon") or s.get("id"), "shape": "polygon" if s.get("geom") == "polygon" else "line",
                "box": _r(s["box"]),
            }, ensure_ascii=False))
    parts.append("DETECTED OBJECTS FROM CALL 1 (boxes are final and in the same 0..1 coordinates):\n" + "\n".join(lines))
    parts.append(
        "OUTPUT FORMAT (only these keys; omit an object entirely when its edge is unclear, better no outline than an invented one):\n"
        "{\"anomalies\":[{\"id\":\"lesion_1\",\"polygon\":[[x,y],[x,y],...]}],"
        "\"structures\":[{\"id\":\"right_lung\",\"polygon\":[[x,y],...]},{\"id\":\"right_hemidiaphragm\",\"polyline\":[[x,y],...]}]}\n"
        "Every x,y is a decimal 0.0 to 1.0 relative to the WHOLE image. Use [] for a list with no outlines."
    )
    return "\n\n".join(parts)


def parse_segmentation_json(raw_content) -> Tuple[Optional[dict], str]:
    """Ambil objek JSON hasil segmentasi: dict dengan kunci 'anomalies' dan/atau 'structures' (nama alternatif ikut diterima)."""
    raw = extract_text(raw_content)
    if not raw or not raw.strip():
        return None, "empty"
    text = _strip_reasoning(raw) or raw
    best, best_mode, best_score = None, "none", 0
    cands = [text] if text.lstrip()[:1] in "{[" else []
    cands += list(_iter_json_objects(text))
    for cand in cands:
        obj, mode = _try_load(cand)
        if isinstance(obj, list):
            obj = next((x for x in obj if isinstance(x, dict)), None)
        if not isinstance(obj, dict):
            continue
        sc = _seg_score(obj)
        if sc > best_score:
            best, best_mode, best_score = obj, mode, sc
    return best, best_mode


_A_KEYS = ("anomalies", "lesions", "anomali", "lesi", "findings")
_S_KEYS = ("structures", "anatomy", "struktur", "organs", "segments")


def _seg_score(obj: dict) -> int:
    low = {str(k).lower() for k in obj}
    return sum(1 for k in _A_KEYS + _S_KEYS if k in low)


def _list_of(obj: dict, keys) -> list:
    low = {str(k).lower(): k for k in obj}
    for k in keys:
        if k in low and isinstance(obj[low[k]], (list, dict)):
            v = obj[low[k]]
            if isinstance(v, dict):
                v = [dict(x, id=x.get("id") or kk) if isinstance(x, dict) else {"id": kk} for kk, x in v.items()]
            return v
    return []


def extract_outlines(obj: dict, img_wh=None, model_lower: str = "") -> Tuple[Dict[str, list], Dict[str, dict]]:
    """Dari keluaran model -> (kontur_lesi {id: polygon}, kontur_organ {taxon: {'polygon'|'polyline': titik}}), koordinat 0..1."""
    from .thorax_anatomy_taxonomy import resolve_taxon
    les: Dict[str, list] = {}
    for it in _list_of(obj, _A_KEYS):
        if not isinstance(it, dict) or not it.get("id"):
            continue
        poly = _poly_of(it, img_wh, model_lower)
        if poly:
            les[str(it["id"])] = poly
    sts: Dict[str, dict] = {}
    for it in _list_of(obj, _S_KEYS):
        if not isinstance(it, dict):
            continue
        tid = resolve_taxon(str(it.get("id") or it.get("taxon") or it.get("label") or ""))
        if not tid:
            continue
        poly, line = _poly_of(it, img_wh, model_lower), _line_of(it, img_wh, model_lower)
        if poly or line:
            sts[tid] = {k: v for k, v in (("polygon", poly), ("polyline", line)) if v}
    return les, sts


def merge_outlines(anomalies: list, structures: list, les: Dict[str, list], sts: Dict[str, dict]) -> Tuple[int, int]:
    """Pasang kontur ke objek hasil panggilan 1 (berdasarkan id). Mengubah daftar di tempat; mengembalikan (jumlah lesi, jumlah organ) yang diberi kontur."""
    n_l = n_s = 0
    for a in anomalies or []:
        poly = les.get(str(a.get("id")))
        if poly and isinstance(a.get("box"), dict):
            a["polygon"] = _clean_points(poly, 3)
            n_l += 1 if a["polygon"] else 0
    for st in structures or []:
        if st.get("derived"):
            continue
        o = sts.get(st.get("taxon"))
        if not o:
            continue
        if o.get("polygon"):
            st["polygon"] = _clean_points(o["polygon"], 3, 60)
            n_s += 1 if st["polygon"] else 0
        elif o.get("polyline"):
            st["polyline"] = _clean_points(o["polyline"], 2, 40)
            n_s += 1 if st["polyline"] else 0
    return n_l, n_s


def is_segmented(anomalies: list, structures: list) -> bool:
    return any(a.get("polygon") for a in anomalies or []) or any(
        (s.get("polygon") or s.get("polyline")) and not s.get("derived") for s in structures or [])
