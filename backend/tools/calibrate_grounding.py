"""Kalibrasi koordinat per model (P3-10).

Mengirim citra sintetis (3 persegi berwarna dengan posisi diketahui) lewat jalur yang sama dengan routers/scan.py
(router AI yang sama, header otorisasi yang sama, parser yang sama), lalu mengukur IoU kotak yang dikembalikan model.

Jalankan dari folder backend/:
    python tools/calibrate_grounding.py kr/claude-sonnet-4.5 oc/mimo-v2.6-flash-free oc/deepseek-v4.1-flash-free

Cara membaca hasil:
  - Tanpa nilai sama sekali      : model kemungkinan tidak melihat gambar -> jangan dipakai untuk analisis citra.
  - IoU rata-rata < 0.5          : model tidak layak untuk koordinat; pakai hanya untuk zona/diagnosis.
  - IoU buruk tetapi bergeser konsisten : koreksi skala di ai_parsers/geometry.py (_COORD_1000_FAMILIES; tambahkan
                                   mimo/deepseek bila ternyata memakai 0..1000).
"""
import asyncio
import base64
import io
import json
import os
import sys

import httpx
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ai_parsers  # noqa: E402
from config import settings, resolve_authorization, max_tokens_for  # noqa: E402

TRUTH = {"red": (0.10, 0.15, 0.30, 0.35), "green": (0.55, 0.20, 0.80, 0.45), "blue": (0.35, 0.60, 0.60, 0.90)}
IOU_OK = 0.5

PROMPT = ("Image size 1024x1024. Return ONLY JSON: {\"objects\":[{\"color\":\"red|green|blue\","
          "\"box\":{\"xmin\":0.0,\"ymin\":0.0,\"xmax\":0.0,\"ymax\":0.0}}]} "
          "with coordinates normalised 0..1 (x right, y down, origin top-left), one box per coloured square.")


def make_image(size=1024):
    im = Image.new("RGB", (size, size), "black")
    d = ImageDraw.Draw(im)
    for name, (x0, y0, x1, y1) in TRUTH.items():
        d.rectangle([x0 * size, y0 * size, x1 * size, y1 * size], fill=name)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode(), (size, size)


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u else 0.0


def _answer_text(msg: dict) -> str:
    """Teks jawaban; kunci 'objects' tidak dikenali filter reasoning umum, jadi cek reasoning_content secara eksplisit."""
    text = ai_parsers.extract_message_text(msg)
    if text.strip():
        return text
    for k in ("reasoning_content", "reasoning", "thinking"):
        alt = ai_parsers.extract_text(msg.get(k))
        if alt and '"objects"' in alt:
            return alt
    return ""


def _parse_objects(text: str):
    """Ambil objek JSON yang memuat kunci 'objects'. TIDAK memakai parse_with_mode: parser itu hanya menerima objek dengan kunci
    hasil radiologi (diagnosis, anomalies, ...), sehingga {"objects": [...]} selalu dibuang dan semua model tampak buta."""
    clean = ai_parsers._strip_reasoning(text or "")
    for cand in ai_parsers._iter_json_objects(clean):
        obj, _ = ai_parsers._try_load(cand)
        if isinstance(obj, list):
            obj = next((x for x in obj if isinstance(x, dict)), None)
        if isinstance(obj, dict) and isinstance(obj.get("objects"), list):
            return obj
    return None


def _verdict(scores: dict) -> str:
    if not scores:
        return "TIDAK ADA NILAI: model mungkin tidak melihat gambar atau tidak memberi kotak -> keluarkan dari daftar model vision"
    mean = sum(scores.values()) / len(scores)
    if len(scores) < len(TRUTH):
        return f"sebagian (hanya {len(scores)}/{len(TRUTH)} objek terbaca), IoU rata-rata {mean:.2f}"
    if mean < IOU_OK:
        return f"IoU rata-rata {mean:.2f} < {IOU_OK}: tidak layak untuk koordinat; pakai hanya untuk zona/diagnosis. Cek juga skala (0..1000?) di geometry.py"
    return f"layak untuk koordinat (IoU rata-rata {mean:.2f})"


async def run(model: str) -> dict:
    b64, wh = make_image()
    payload = {"model": model, "temperature": 0.0, "max_tokens": max_tokens_for(model), "stream": False,
               "messages": [{"role": "user", "content": [
                   {"type": "text", "text": PROMPT},
                   {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]}
    headers = {"Content-Type": "application/json"}
    auth = resolve_authorization(None)
    if auth:
        headers["Authorization"] = auth
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(settings.NINEROUTER_URL, json=payload, headers=headers)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}", "scores": {}}
    data = r.json()
    msg = ((data.get("choices") or [{}])[0] or {}).get("message") or {}
    obj = _parse_objects(_answer_text(msg))
    scores, boxes = {}, {}
    for o in (obj or {}).get("objects", []):
        if not isinstance(o, dict):
            continue
        nb = ai_parsers.geometry._norm_box(o, wh, model.lower())
        col = str(o.get("color", "")).lower()
        if nb and col in TRUTH:
            box = (nb["xmin"], nb["ymin"], nb["xmax"], nb["ymax"])
            scores[col] = round(iou(box, TRUTH[col]), 3)
            boxes[col] = [round(v, 3) for v in box]
    return {"scores": scores, "boxes": boxes, "verdict": _verdict(scores)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for m in sys.argv[1:]:
        try:
            res = asyncio.run(run(m))
        except Exception as e:  # noqa: BLE001
            res = {"error": f"{type(e).__name__}: {e}", "scores": {}}
        print(m, json.dumps(res, ensure_ascii=False))
