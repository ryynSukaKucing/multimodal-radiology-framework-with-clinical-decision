import io
import os
import uuid

import numpy as np
import pydicom
from PIL import Image

from config import settings


def is_dicom_filename(filename: str) -> bool:
    return filename.lower().endswith('.dcm')


class DicomReadError(Exception):
    """Error yang ramah-pengguna saat DICOM gagal dibaca/didekompresi."""
    pass


def dicom_bytes_to_pil(file_bytes: bytes) -> Image.Image:
    try:
        dicom_data = pydicom.dcmread(io.BytesIO(file_bytes))
    except Exception as e:
        raise DicomReadError(f"Berkas bukan DICOM valid atau rusak: {e}")

    try:
        pixel_array = dicom_data.pixel_array
    except Exception as e:
        msg = str(e)
        if "handler" in msg.lower() or "decompress" in msg.lower() or "libjpeg" in msg.lower() or "openjpeg" in msg.lower():
            raise DicomReadError(
                "Failed to decompress DICOM pixel data (compressed transfer syntax, e.g. JPEG/JPEG2000). "
                "Make sure pylibjpeg, pylibjpeg-libjpeg & pylibjpeg-openjpeg are installed "
                "(re-run setup.bat run so the new dependencies get installed)."
            )
        raise DicomReadError(f"Failed to read DICOM pixel data: {e}")

    # Berkas multi-frame (satu file berisi banyak slice/CINE) -> ambil slice tengah untuk pratinjau.
    if pixel_array.ndim == 3 and pixel_array.shape[0] > 1 and pixel_array.shape[-1] not in (3, 4):
        pixel_array = pixel_array[pixel_array.shape[0] // 2]
    elif pixel_array.ndim == 4:
        pixel_array = pixel_array[pixel_array.shape[0] // 2]

    pixel_array = pixel_array.astype(float)

    # Terapkan Rescale Slope/Intercept bila ada (standar untuk CT, nilai HU) sebelum windowing.
    slope = float(getattr(dicom_data, "RescaleSlope", 1) or 1)
    intercept = float(getattr(dicom_data, "RescaleIntercept", 0) or 0)
    pixel_array = pixel_array * slope + intercept

    rng = pixel_array.max() - pixel_array.min()
    if rng == 0:
        rng = 1
    pixel_array = (pixel_array - pixel_array.min()) / rng * 255.0
    pixel_array = np.clip(pixel_array, 0, 255).astype('uint8')

    if pixel_array.ndim == 3 and pixel_array.shape[-1] in (3, 4):
        return Image.fromarray(pixel_array[:, :, :3], mode='RGB')
    return Image.fromarray(pixel_array).convert('L')


def extract_dicom_meta(file_bytes: bytes) -> dict:
    """Metadata ringan DICOM untuk overlay viewer (pixel spacing, WW/WL, tanggal/jam studi, proyeksi)."""
    try:
        ds = pydicom.dcmread(io.BytesIO(file_bytes), stop_before_pixels=True)
    except Exception:
        return {}

    def first(v):
        try:
            if hasattr(v, '__iter__') and not isinstance(v, (str, bytes)):
                v = list(v)[0]
            return float(v)
        except Exception:
            return None

    spacing = getattr(ds, 'PixelSpacing', None) or getattr(ds, 'ImagerPixelSpacing', None)
    px_mm = None
    if spacing is not None:
        try:
            px_mm = float(list(spacing)[0])
        except Exception:
            px_mm = None

    def fmt_date(d):
        d = str(d or '')
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]}" if len(d) >= 8 else ''

    def fmt_time(t):
        t = str(t or '')
        return f"{t[0:2]}:{t[2:4]}" if len(t) >= 4 else ''

    return {
        'pixel_spacing_mm': px_mm,
        'window_width': first(getattr(ds, 'WindowWidth', None)),
        'window_center': first(getattr(ds, 'WindowCenter', None)),
        'study_date': fmt_date(getattr(ds, 'StudyDate', '')),
        'study_time': fmt_time(getattr(ds, 'StudyTime', '')),
        'projection': str(getattr(ds, 'ViewPosition', '') or ''),
        'modality': str(getattr(ds, 'Modality', '') or ''),
    }


def save_uploaded_file(filename: str, file_bytes: bytes):
    """
    Menyimpan berkas asli yang diunggah, dan jika berkas DICOM, membuat pula
    versi pratinjau JPEG agar bisa ditampilkan langsung di browser.

    Returns: (stored_filename, preview_filename, is_dicom, base64_jpeg_for_ai)
    """
    import base64

    ext = os.path.splitext(filename)[1].lower() or '.bin'
    unique_id = uuid.uuid4().hex[:12]
    stored_filename = f"{unique_id}{ext}"
    stored_path = os.path.join(settings.UPLOAD_DIR, stored_filename)

    with open(stored_path, 'wb') as f:
        f.write(file_bytes)

    if is_dicom_filename(filename):
        image = dicom_bytes_to_pil(file_bytes)
        preview_filename = f"{unique_id}_preview.jpg"
        preview_path = os.path.join(settings.UPLOAD_DIR, preview_filename)
        image.save(preview_path, format='JPEG', quality=92)

        buffered = io.BytesIO()
        image.save(buffered, format='JPEG', quality=92)
        base64_jpeg = base64.b64encode(buffered.getvalue()).decode('utf-8')

        return stored_filename, preview_filename, True, base64_jpeg

    # Bukan DICOM: pratinjau = berkas itu sendiri
    base64_jpeg = base64.b64encode(file_bytes).decode('utf-8')
    return stored_filename, stored_filename, False, base64_jpeg


AI_IMAGE_LONG_SIDE = 1024


def prepare_ai_image(base64_jpeg: str, long_side: int = AI_IMAGE_LONG_SIDE):
    """Skala tetap untuk AI: sisi panjang maksimal 1024 px (rasio dijaga, EXIF diluruskan).
    Mengembalikan (base64_jpeg_baru, (lebar, tinggi)). Ukuran itu disebut di prompt dan dipakai parser,
    jadi koordinat piksel dari model tidak lagi dibagi dimensi citra asli yang berbeda skala."""
    import base64
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(base64.b64decode(base64_jpeg)))
        im = ImageOps.exif_transpose(im).convert('RGB')
        w, h = im.size
        sc = long_side / max(w, h)
        if sc < 1.0:
            im = im.resize((max(1, round(w * sc)), max(1, round(h * sc))), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format='JPEG', quality=92)
        return base64.b64encode(buf.getvalue()).decode('utf-8'), im.size
    except Exception:
        return base64_jpeg, None


def _longest_run(flags, max_gap: int):
    """Rentang terpanjang indeks bernilai True, dengan celah False <= max_gap dianggap menyambung. (awal, akhir_eksklusif) atau None."""
    best, start, last, gap = None, None, None, 0
    for i, f in enumerate(list(flags) + [False] * (max_gap + 2)):
        if f:
            if start is None:
                start = i
            last, gap = i, 0
        elif start is not None:
            gap += 1
            if gap > max_gap:
                if best is None or (last - start) > (best[1] - 1 - best[0]):
                    best = (start, last + 1)
                start = None
    return best


def content_bbox(base64_jpeg: str):
    """Lapang pandang citra: kotak (x0, y0, x1, y1) ternormalisasi 0..1 yang berisi gambar, tanpa bingkai/tepi hitam.
    None bila citra memenuhi bingkai (tidak ada tepi hitam berarti) atau tidak bisa dianalisis. Dipakai untuk memberi tahu model
    area gambar yang sebenarnya dan menolak struktur yang jatuh di area hitam."""
    import base64
    from PIL import Image, ImageOps
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(base64.b64decode(base64_jpeg)))).convert('L')
        n = 128
        im = im.resize((n, n), Image.BILINEAR)
        px = list(im.getdata())
        srt = sorted(px)
        thr = max(14, int(0.12 * srt[int(len(srt) * 0.98)]))
        on = [1 if v > thr else 0 for v in px]
        cols = [sum(on[y * n + x] for y in range(n)) / n >= 0.08 for x in range(n)]
        rows = [sum(on[y * n + x] for x in range(n)) / n >= 0.08 for y in range(n)]
        rx, ry = _longest_run(cols, 4), _longest_run(rows, 4)
        if not rx or not ry:
            return None
        x0, x1, y0, y1 = rx[0] / n, rx[1] / n, ry[0] / n, ry[1] / n
        if (x1 - x0) < 0.2 or (y1 - y0) < 0.2:
            return None
        if (x1 - x0) >= 0.93 and (y1 - y0) >= 0.93:
            return None
        pad = 0.01
        return (round(max(0.0, x0 - pad), 3), round(max(0.0, y0 - pad), 3), round(min(1.0, x1 + pad), 3), round(min(1.0, y1 + pad), 3))
    except Exception:
        return None
