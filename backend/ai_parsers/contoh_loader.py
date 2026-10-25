"""Pemuat contoh dataset teks (JSONL) untuk few-shot prompt.

Setiap folder tahap (deteksi_anatomi, deteksi_lesi, segmentasi_anatomi, segmentasi_lesi, diagnosa_medis) punya
`contoh.jsonl`: satu baris = satu pasangan {"prompt": ..., "jawaban": ..., "status": ...}. Murni teks, tanpa gambar.

Hanya baris berstatus 'verified' (sudah dicek manusia) atau 'contoh' (contoh awal buatan) yang dipakai.
Baris 'ai_draft' / 'rejected' tidak pernah disisipkan ke prompt.
"""
import json
import os
import re
from typing import List

STATUS_DIPAKAI = ("verified", "contoh")
MAKS_KARAKTER_BLOK = 2500


def _token(s: str) -> set:
    return set(re.findall(r"[a-z0-9]{3,}", (s or "").lower()))


def baca_contoh(folder: str) -> List[dict]:
    path = os.path.join(folder, "contoh.jsonl")
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("status", "contoh") in STATUS_DIPAKAI and r.get("prompt") and "jawaban" in r:
                rows.append(r)
    return rows


def blok_contoh(folder: str, kueri: str = "", maks: int = 2, judul: str = "FORMAT EXAMPLES") -> str:
    """Pilih `maks` contoh yang paling mirip dengan `kueri` (tumpang-tindih kata), kembalikan blok teks siap sisip."""
    rows = baca_contoh(folder)
    if not rows or maks <= 0:
        return ""
    q = _token(kueri)
    rows.sort(key=lambda r: -len(q & _token(r.get("prompt", "") + " " + " ".join(r.get("tag", [])))))
    out, total = [], 0
    for r in rows[:maks]:
        ans = r["jawaban"] if isinstance(r["jawaban"], str) else json.dumps(r["jawaban"], ensure_ascii=False)
        item = f"- Input: {r['prompt']}\n  Output: {ans}"
        if total + len(item) > MAKS_KARAKTER_BLOK:
            break
        out.append(item)
        total += len(item)
    if not out:
        return ""
    return (f"{judul} (imitate only the FORMAT and the way of reasoning. Placeholders such as <left> or <x> stand for numbers you must "
            "measure yourself on the image you see; never copy example values, and never output a placeholder as a value):\n" + "\n".join(out))
