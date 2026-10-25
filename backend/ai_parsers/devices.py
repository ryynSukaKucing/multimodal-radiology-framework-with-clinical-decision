import re

DEVICE_KEYWORDS = (
    "kateter", "catheter", "guidewire", "guide wire", "guiding", "kawat", "wire", "balon", "balloon", "stent",
    "pacemaker", "elektroda", "electrode", "lead ", "selang", "tube", "ett", "ngt", "drain", "klip", "clip",
    "implan", "implant", "alat ", "device", "perangkat",
)


# frasa yang justru klinis (mis. "restenosis in-stent") tetap boleh lewat
DEVICE_ALLOW = ("in-stent", "in stent", "restenosis", "trombosis stent", "stent thrombosis", "malposisi", "malposition",
                "migrasi", "migration", "fraktur stent", "komplikasi")


def strip_device_findings(anomalies):
    """Buang 'anomalies' yang sebenarnya hanyalah objek alat medis (bukan kelainan pasien).
    Mengembalikan (anomalies_bersih, daftar_label_alat_yang_dibuang)."""
    kept, removed = [], []
    for a in anomalies or []:
        text = f"{a.get('label', '')} {a.get('id', '')}".lower() + " "
        if any(k in text for k in DEVICE_KEYWORDS) and not any(k in text for k in DEVICE_ALLOW):
            removed.append(a.get("label") or a.get("id") or "alat")
        else:
            kept.append(a)
    return kept, removed


# Bukan lesi paru: bayangan jaringan lunak/kulit/payudara, lipatan kulit, artefak. Model lemah sering menandainya sebagai "opasitas" kecil di zona bawah.
NONLESION_RX = re.compile(
    r"(soft[- ]tissue (?:overlay|shadow|density|projection)|jaringan lunak (?:overlay|tumpang)|subcutaneous|subkutan|skin fold|lipatan kulit|"
    r"nipple|puting|breast (?:shadow|tissue|overlay)|bayangan payudara|artifact|artefak|motion blur|overlay)", re.I)


def strip_nonlesion_findings(anomalies):
    """Buang 'anomalies' yang hanya bayangan jaringan lunak/artefak (bukan kelainan paru). Mengembalikan (bersih, label_yang_dibuang)."""
    kept, removed = [], []
    for a in anomalies or []:
        text = f"{a.get('label', '')} {a.get('description', '')}"
        if NONLESION_RX.search(text):
            removed.append(a.get("label") or a.get("id") or "finding")
        else:
            kept.append(a)
    return kept, removed
