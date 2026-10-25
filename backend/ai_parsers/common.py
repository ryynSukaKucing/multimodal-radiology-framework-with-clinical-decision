EXPECTED_KEYS = ("diagnosis", "confidence", "summary", "anomalies", "diagnosis_alternatif")


def _num(v):
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def _as_text(v) -> str:
    if v is None:
        return ''
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (list, tuple)):
        return '; '.join(x for x in (_as_text(i) for i in v) if x)
    if isinstance(v, dict):
        for k in ('name', 'label', 'diagnosis', 'text', 'description'):
            if v.get(k):
                return _as_text(v[k])
        return '; '.join(f'{k}: {_as_text(x)}' for k, x in v.items() if x not in (None, ''))
    return str(v)
