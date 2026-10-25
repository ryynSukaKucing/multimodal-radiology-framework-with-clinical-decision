# ai_parsers — peta folder tahap analisis toraks

Tiap tahap punya folder sendiri. Isi folder: `prompt.py` (aturan), `contoh.jsonl` (dataset teks), dan kode koreksi bila ada.

| Folder | Tugas | Output yang diatur | Koreksi kode |
|---|---|---|---|
| `deteksi_anatomi/`   | deteksi struktur normal (label + box) | `structures[].label/box` | - |
| `deteksi_lesi/`      | deteksi kelainan (label + box + severity) | `anomalies[].label/box` | - |
| `segmentasi_anatomi/`| kontur struktur normal | `structures[].polygon` | `fix_laterality` (kiri/kanan tertukar) |
| `segmentasi_lesi/`   | kontur kelainan | `anomalies[].polygon` | `refine_anomaly_geometry` (jepit ke paru, tandai terlalu luas) |
| `diagnosa_medis/`    | temuan -> diagnosis, banding, keyakinan | `diagnosis`, `diagnosis_alternatif`, `confidence` | `reconcile_thorax_diagnosis` |

Perakit prompt: `prompts/builder.py`. Aturan umum koordinat: `prompts/geometry_notes.py`. Prompt dasar per model: `prompts/base.py`.

## Dataset teks (`contoh.jsonl`)
Satu baris = satu contoh, murni teks:
`{"id":"...","status":"contoh|verified|ai_draft|rejected","tag":["kata","kunci"],"prompt":"...","jawaban":{...}}`
- Hanya `verified` dan `contoh` yang disisipkan ke prompt (maks 1-2 per tahap, dipilih lewat kemiripan kata dengan area + konteks klinis).
- `ai_draft` dan `rejected` tidak pernah dipakai. Baris berawalan `#` diabaikan.
- Seluruh baris awal berstatus `contoh` (buatan, belum diverifikasi radiolog). Ganti/tambah dengan kasus nyata yang sudah dicek, lalu beri `verified`.


## Alur dua panggilan (v27): deteksi objek lalu segmentasi

Pemindaian dipecah supaya tiap panggilan pendek dan fokus (sebelumnya satu panggilan menulis kotak, kontur, diagnosis, dan SOAP sekaligus, sehingga JSON mudah terpotong dan kotak melenceng).

| Panggilan | Endpoint | Isi permintaan | Keluaran | max_tokens |
|---|---|---|---|---|
| 1. Deteksi objek | `POST /api/scan`, `/api/scan/batch` | `build_dynamic_system_prompt(..., stage="detect")`: tahap 1 dan 2 + diagnosis, tanpa tahap 3 dan 4 | kotak organ dan lesi, severity, diagnosis, SOAP | minimal 8000 (`DETECT_MAX_TOKENS`) |
| 2. Segmentasi | `POST /api/scan/{history_id}/segment` (tombol Segmentasi) | `segmentasi_tahap.build_segmentation_prompt`: citra yang sama + kotak final dari panggilan 1 | polygon lesi, polygon/polyline organ per id | minimal 8000 (`SEGMENT_MAX_TOKENS`) |

- Batas token tidak pernah di bawah `TOKEN_FLOOR` (8000); model berpikir memakai `*_THINKING` (16000).
- Kotak dari panggilan 1 final. Panggilan 2 hanya menambah kontur, lalu kontur divalidasi (`sanitize_anomaly_geometry`, `reconcile_structures_ex`, `refine_anomaly_geometry`). Zona paru diturunkan dari kontur paru setelah segmentasi.
- Kontur yang nyasar pada panggilan 1 dibuang. Bila segmentasi gagal, hasil deteksi tidak berubah dan tombol bisa ditekan lagi.
- `scan_history.segmented` (0/1) menandai status segmentasi; riwayat lama yang sudah berkontur otomatis dianggap tersegmentasi.
- `GROUNDING_PASS` bawaannya `false` agar total panggilan tetap dua. Aktifkan bila ingin lintasan ketiga (CTR dan lokalisasi tambahan).
