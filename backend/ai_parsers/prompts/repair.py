import re

REPAIR_PROMPT = (
    "Convert the following radiology analysis text into ONE valid JSON object with keys: "
    '"diagnosis" (string), "diagnosis_alternatif" (array of strings), "confidence" (number 0..1), "summary" (string), '
    '"anomalies" (array of objects: id, label, severity "High"/"Moderate"/"Low", description, '
    'box {xmin,ymin,xmax,ymax} 0..1 and polygon [[x,y],...] 0..1 if the coordinates are in the text) and "structures" (array of objects: id, label, '
    'box, polygon, if present in the text). Keep the content as is and do not add new findings. '
    "If the text below is NOT a radiology analysis (for example a command, an error message, an apology, or empty), "
    'reply exactly {"error":"not_radiology_text"} and nothing else. '
    "Reply with RAW JSON only, no markdown.\n\nTEXT:\n"
)


_REFUSAL_RX = re.compile(r'"error"\s*:\s*"not_radiology_text"', re.I)


def repair_refused(text) -> bool:
    """True bila model repair menjawab bahwa teks masukan bukan analisis radiologi (lihat REPAIR_PROMPT).
    Dicek pada teks mentah karena parser JSON tidak menganggap {"error": ...} sebagai hasil analisis."""
    return bool(text) and bool(_REFUSAL_RX.search(str(text)))
