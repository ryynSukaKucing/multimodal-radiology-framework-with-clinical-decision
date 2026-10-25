import re
from .common import _as_text
from .text_extract import _strip_reasoning, extract_text
from .json_repair import _score_obj, parse_with_mode
from .geometry import _POLY_KEYS, _box_from_poly, _norm_box, _poly_of, normalize_structures
from .thorax_anatomy_taxonomy import TAXA, resolve_taxon
from .prompts.modes import band_of_score


_SEV_MAP = (
    (('tinggi', 'high', 'critical', 'severe', 'berat', 'darurat', 'urgent', 'kritis'), 'High'),
    (('sedang', 'moderate', 'medium', 'menengah'), 'Moderate'),
    (('rendah', 'low', 'mild', 'ringan', 'minor'), 'Low'),
)


_ALIASES = {
    'diagnosis': ('diagnosa', 'primary_diagnosis', 'main_diagnosis', 'diagnosis_utama', 'impression', 'kesan'),
    'summary': ('ringkasan', 'ringkasan_temuan', 'findings_summary', 'interpretation', 'report', 'temuan', 'description'),
    'anomalies': ('anomali', 'abnormalities', 'lesions', 'findings', 'kelainan', 'detections'),
    'diagnosis_alternatif': ('diagnosis_banding', 'differential_diagnosis', 'differentials', 'alternative_diagnoses',
                             'diagnosis_alternative', 'differential'),
    'confidence': ('keyakinan', 'tingkat_keyakinan', 'confidence_score', 'probability', 'score'),
    'structures': ('struktur', 'struktur_anatomi', 'anatomical_structures', 'anatomy', 'segments', 'organs', 'segmentation'),
}


def _unwrap(d: dict) -> dict:
    for _ in range(3):
        if any(k in d for k in ('diagnosis', 'diagnosa')):
            return d
        for k in ('result', 'results', 'data', 'response', 'output', 'analysis', 'report', 'hasil'):
            v = d.get(k)
            if isinstance(v, dict) and _score_obj(v) >= 5:
                d = v
                break
        else:
            return d
    return d


def _to_float01(v) -> float:
    if isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        x = float(v)
    elif isinstance(v, str):
        s = v.strip().lower()
        m = re.search(r'-?\d+(?:[.,]\d+)?', s)
        if m:
            x = float(m.group(0).replace(',', '.'))
            if '%' in s and x <= 1.0:
                x *= 100.0
        else:
            return {'tinggi': .85, 'high': .85, 'sedang': .6, 'medium': .6, 'moderate': .6, 'rendah': .35, 'low': .35}.get(s, 0.0)
    else:
        return 0.0
    if x != x:
        return 0.0
    if x > 1.0:
        x = x / 100.0 if x <= 100.0 else 1.0
    return round(min(1.0, max(0.0, x)), 4)


def _norm_severity(v) -> str:
    s = str(v or '').strip().lower()
    for keys, label in _SEV_MAP:
        if any(k in s for k in keys):
            return label
    return str(v).strip() if v else 'Moderate'


# Skor bawaan bila model tidak memberi 'severity_score' (diturunkan dari label severity).
_SEV_DEFAULT_SCORE = {'High': 0.82, 'Moderate': 0.5, 'Low': 0.2}
_SCORE_KEYS = ('severity_score', 'skor_keparahan', 'derajat_keparahan', 'severity_degree', 'severity_level', 'keparahan_skor', 'heat', 'heat_score')


def _norm_severity_score(a: dict, severity_label: str):
    """Kembalikan (skor 0..1, dari_model: bool). Skor dipakai heatmap lesi: 0 biru (aman) ... 1 merah (parah)."""
    for k in _SCORE_KEYS:
        v = a.get(k)
        if v is None or isinstance(v, bool) or (isinstance(v, str) and not v.strip()):
            continue
        if isinstance(v, str) and not re.search(r'\d', v):
            continue                                   # teks tanpa angka (mis. 'tinggi') bukan skor numerik
        x = _to_float01(v)
        return round(x, 3), True
    return _SEV_DEFAULT_SCORE.get(severity_label, 0.5), False


_LOK_KEYS = ('lokasi_anatomi', 'anatomy_ref', 'anatomi_ref', 'anatomical_location', 'lokasi_taksonomi', 'taxon', 'taxa')


def _norm_lokasi(a: dict) -> list:
    """Lokasi anatomi lesi dari model -> daftar id taksonomi valid (id baku atau teks bebas yang bisa dipetakan)."""
    raw = None
    for k in _LOK_KEYS:
        if a.get(k) not in (None, '', [], {}):
            raw = a.pop(k)
            break
    for k in _LOK_KEYS:
        a.pop(k, None)
    if raw is None:
        return []
    if isinstance(raw, (str, dict)):
        raw = [raw]
    out = []
    for x in raw if isinstance(raw, list) else []:
        tid = resolve_taxon(_as_text(x))
        if tid and tid not in out:
            out.append(tid)
    return out[:4]


def normalize_result(d: dict, img_wh=None, model_lower: str = '', fov=None) -> dict:
    """Menyeragamkan skema hasil model agar renderer frontend tidak pecah pada keluaran 'longgar'."""
    d = dict(_unwrap(d))
    lower = {str(k).lower().strip(): k for k in d.keys()}
    for canon, alts in _ALIASES.items():
        if canon in d and d[canon] not in (None, '', [], {}):
            continue
        for a in alts:
            if a in lower and d[lower[a]] not in (None, '', [], {}):
                if canon == 'anomalies' and not isinstance(d[lower[a]], (list, dict)):
                    continue
                if canon == 'confidence' and a == 'score' and isinstance(d[lower[a]], (list, dict)):
                    continue
                d[canon] = d[lower[a]]
                break

    d['diagnosis'] = _as_text(d.get('diagnosis')) or 'Unidentified'
    d['confidence'] = _to_float01(d.get('confidence'))
    d['summary'] = _as_text(d.get('summary'))
    alt = d.get('diagnosis_alternatif')
    if isinstance(alt, str):
        alt = [x.strip() for x in re.split(r'[;\n]|\s\|\s', alt) if x.strip()]
    elif isinstance(alt, dict):
        alt = [alt]
    d['diagnosis_alternatif'] = [t for t in (_as_text(x) for x in (alt or [])) if t][:8]

    an = d.get('anomalies')
    if isinstance(an, dict):
        an = [an]
    items = []
    for i, a in enumerate(an if isinstance(an, list) else [], start=1):
        if isinstance(a, str):
            a = {'label': a}
        if not isinstance(a, dict):
            continue
        a = dict(a)
        a['id'] = str(a.get('id') or f'lesion_{i}')
        a['label'] = _as_text(a.get('label') or a.get('name') or a.get('finding') or a.get('nama')) or f'Abnormality {i}'
        a['severity'] = _norm_severity(a.get('severity') or a.get('tingkat') or a.get('keparahan'))
        a['description'] = _as_text(a.get('description') or a.get('deskripsi') or a.get('detail') or a.get('location'))
        score, from_model = _norm_severity_score(a, a['severity'])
        for k in _SCORE_KEYS:
            if k != 'severity_score':
                a.pop(k, None)
        a['severity_score'] = score
        if from_model:
            a['severity'] = band_of_score(score)           # label dibuat konsisten dengan skor numerik
        a['severity_score_source'] = 'model' if from_model else 'derived'
        a['lokasi_anatomi'] = _norm_lokasi(a)
        box = _norm_box(a, img_wh, model_lower)
        poly = _poly_of(a, img_wh, model_lower)
        for k in _POLY_KEYS:
            if k != 'polygon':
                a.pop(k, None)
        if poly:
            a['polygon'] = poly
            if not box:
                box = _box_from_poly(poly)                # segmentasi tanpa kotak: kotak diturunkan dari kontur
        else:
            a.pop('polygon', None)
        if box:
            a['box'] = box
            if not isinstance(a.get('pointer'), dict):
                a['pointer'] = {
                    'targetX': round((box['xmin'] + box['xmax']) / 2, 4), 'targetY': round((box['ymin'] + box['ymax']) / 2, 4),
                    'labelX': round(min(0.95, box['xmax'] + 0.03), 4), 'labelY': round(max(0.05, box['ymin'] - 0.03), 4),
                }
        else:
            a.pop('box', None)
        items.append(a)
    d['anomalies'] = items
    notes = []
    d['structures'] = normalize_structures(d.get('structures'), img_wh, model_lower, fov=fov, report=notes)
    if notes:
        d['_struct_notes'] = notes                      # read and removed by the scan router (log)
    soap = d.get('soap')
    if isinstance(soap, str) and soap.strip():
        soap = {'assessment': soap.strip()}
    if isinstance(soap, dict):
        keys = ('subjective', 'objective', 'assessment', 'plan')
        low = {str(k).lower()[:1]: v for k, v in soap.items()}   # S/O/A/P atau nama panjang
        norm = {k: _as_text(soap.get(k) if soap.get(k) is not None else low.get(k[0])) for k in keys}
        d['soap'] = norm if any(norm.values()) else None
        if d['soap'] is None:
            d.pop('soap')
    else:
        d.pop('soap', None)
    return d


def text_fallback_result(raw_content) -> dict:
    """Jaring pengaman terakhir: model menjawab prosa tanpa JSON. Hasil ditandai jelas agar tidak disangka valid."""
    text = _strip_reasoning(extract_text(raw_content)) or extract_text(raw_content)
    text = re.sub(r'\s+', ' ', text).strip()
    m = re.search(r'(?:diagnosis|diagnosa|impression|kesan)[^:\n]{0,30}[:\-]\s*([^\n.;]{3,160})', text, re.I)
    return {
        'diagnosis': m.group(1).strip() if m else 'Unidentified (model response was not JSON)',
        'confidence': 0.0,
        'summary': (text[:1500] + ('…' if len(text) > 1500 else '')) or '-',
        'diagnosis_alternatif': [],
        'anomalies': [],
        'parse_mode': 'text_fallback',
        'catatan_parser': 'The model did not return JSON; the summary was taken from the raw text and contains no locations (boxes). Try again or choose another model.',
    }


def parse_model_response(model_lower: str, raw_content, img_wh=None):
    """Titik masuk tunggal untuk semua model. Mengembalikan dict ternormalisasi atau None."""
    obj, _mode = parse_with_mode(raw_content)
    return normalize_result(obj, img_wh, model_lower) if isinstance(obj, dict) else None
