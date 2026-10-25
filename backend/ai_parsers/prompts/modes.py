"""Scan modes (Anatomy / Lesions / Anatomy + Lesions), imaging-type notes, and the lesion severity parameter."""

MODE_ANATOMI = "anatomi"
MODE_LESI = "lesi"
MODE_ANATOMI_LESI = "anatomi_lesi"
MODE_VALID = (MODE_ANATOMI, MODE_LESI, MODE_ANATOMI_LESI)
MODE_LABEL = {MODE_ANATOMI: "Anatomy", MODE_LESI: "Lesions", MODE_ANATOMI_LESI: "Anatomy + Lesions"}


def normalize_mode(v) -> str:
    """Terima 'anatomi' / 'lesi' / 'anatomi_lesi' (toleran terhadap spasi, '+', '-') -> salah satu dari MODE_VALID."""
    s = str(v or "").strip().lower().replace("+", " ").replace("-", " ").replace("_", " ")
    s = " ".join(s.split())
    has_a, has_l = "anatomi" in s or "anatomy" in s, "lesi" in s or "lesion" in s
    if has_a and has_l:
        return MODE_ANATOMI_LESI
    if has_a:
        return MODE_ANATOMI
    if has_l:
        return MODE_LESI
    return MODE_ANATOMI_LESI


def mode_has_anatomy(mode: str) -> bool:
    return mode in (MODE_ANATOMI, MODE_ANATOMI_LESI)


def mode_has_lesion(mode: str) -> bool:
    return mode in (MODE_LESI, MODE_ANATOMI_LESI)


# Explicit instructions per mode: which fields MUST be filled and which MUST stay empty.
MODE_INSTRUCTIONS = {
    MODE_ANATOMI: (
        "SCAN MODE = ANATOMY ONLY. Only anatomical structures are scanned: run anatomical object detection (stage 1) and "
        "anatomical segmentation (stage 3). Fill \"structures\" using Thorax_Anatomy_Taxonomy ids (box; polygon/polyline when the edges are clear). "
        "\"anomalies\" MUST be an empty array [] - do not detect or outline lesions in this mode. "
        "\"diagnosis\" = anatomical impression (e.g. 'Thoracic anatomy appears normal' or a variant/deformity that is actually visible, such as "
        "cardiomegaly or tracheal deviation); \"diagnosis_alternatif\" may be empty. "
        "\"summary\" names the structures assessed and their condition."
    ),
    MODE_LESI: (
        "SCAN MODE = LESIONS ONLY. Only lesions/abnormalities are scanned: run lesion object detection (stage 2) and lesion "
        "segmentation (stage 4). \"structures\" MUST be an empty array [] - do not draw normal anatomical structures in this mode. "
        "Still state the side and anatomical zone in each lesion label/description (e.g. 'right middle zone') because that "
        "defines its location; also fill \"lokasi_anatomi\" (taxonomy ids) for every lesion. Fill each lesion's \"severity_score\" (see SEVERITY PARAMETER). "
        "Diagnosis, differential diagnosis, and diagnosis code are still filled from the lesions found."
    ),
    MODE_ANATOMI_LESI: (
        "SCAN MODE = ANATOMY + LESIONS. Run all four stages: anatomical detection + segmentation ('structures') and lesion detection + "
        "segmentation ('anomalies'). Normal structures only in 'structures', abnormalities only in 'anomalies'. "
        "Fill each lesion's \"severity_score\" (see SEVERITY PARAMETER). The diagnosis is built from all findings."
    ),
}


# Call 1 (object detection only): same modes, but boxes only. Outlines are requested later in a separate segmentation call.
MODE_INSTRUCTIONS_DETECT = {
    MODE_ANATOMI: (
        "SCAN MODE = ANATOMY ONLY, STAGE = OBJECT DETECTION ONLY. Run anatomical object detection (stage 1) only. Fill \"structures\" with "
        "Thorax_Anatomy_Taxonomy ids, each with a BOX only. Do NOT output polygon, polyline, centerline or keypoints: segmentation is a separate request made later. "
        "\"anomalies\" MUST be an empty array [] - do not detect lesions in this mode. "
        "\"diagnosis\" = anatomical impression (e.g. 'Thoracic anatomy appears normal' or a variant/deformity that is actually visible, such as "
        "cardiomegaly or tracheal deviation); \"diagnosis_alternatif\" may be empty. \"summary\" names the structures assessed and their condition."
    ),
    MODE_LESI: (
        "SCAN MODE = LESIONS ONLY, STAGE = OBJECT DETECTION ONLY. Run lesion object detection (stage 2) only. Every lesion gets a tight BOX only. "
        "Do NOT output polygon, polyline, centerline or keypoints: segmentation is a separate request made later. "
        "\"structures\" MUST be an empty array [] - do not draw normal anatomical structures in this mode. "
        "Still state the side and anatomical zone in each lesion label/description (e.g. 'right middle zone') because that "
        "defines its location; also fill \"lokasi_anatomi\" (taxonomy ids) for every lesion. Fill each lesion's \"severity_score\" (see SEVERITY PARAMETER). "
        "Diagnosis, differential diagnosis, and diagnosis code are still filled from the lesions found."
    ),
    MODE_ANATOMI_LESI: (
        "SCAN MODE = ANATOMY + LESIONS, STAGE = OBJECT DETECTION ONLY. Run anatomical detection ('structures') and lesion detection ('anomalies'), "
        "BOXES ONLY. Do NOT output polygon, polyline, centerline or keypoints: segmentation is a separate request made later. "
        "Normal structures only in 'structures', abnormalities only in 'anomalies'. "
        "Fill each lesion's \"severity_score\" (see SEVERITY PARAMETER). The diagnosis is built from all findings."
    ),
}

DETECT_ONLY_NOTE = (
    "OBJECT DETECTION ONLY (call 1 of 2): output only what is needed to LOCATE objects. Every 'structures' and 'anomalies' object has a tight box and "
    "NOTHING for outlines (no polygon, polyline, centerline, keypoints, mask). Keep each 'description' under 25 words. Spend your effort on getting each "
    "box exactly on the object it names, on the correct side (PA/AP: patient's right = image-left), instead of on long text. "
    "A second request will later outline these same boxes, so the box coordinates you write now are final."
)


# Severity parameter -> used by the viewer for the lesion heatmap (blue = safest ... red = most severe).
SEVERITY_SCORE_PROMPT = (
    "LESION SEVERITY PARAMETER: every object in 'anomalies' MUST have a \"severity_score\" decimal 0.0-1.0 "
    "(0.0 = safest/insignificant, 1.0 = most severe/life-threatening). Guide: 0.00-0.33 low (small/residual finding, "
    "stable, no functional impairment); 0.34-0.66 moderate (extensive/active, needs scheduled follow-up); 0.67-1.00 high "
    "(extensive, cavitation, massive effusion/pneumothorax, compression/shift of structures, or needs immediate management). "
    "\"severity\" (Low/Moderate/High) MUST be consistent with the score range. Differentiate values between lesions according to extent, "
    "density, and impact; do not give every lesion the same score. The score is an assessment from the image, not a "
    "calibrated measurement."
)


MODALITAS_NOTES = {
    "x-ray": (
        "Imaging type: X-RAY (2D projection radiography). Structures overlap; assess projection (PA/AP/lateral), rotation, "
        "inspiration. Use the terms opacity/lucency, not HU values."
    ),
    "ct-scan": (
        "Imaging type: CT-SCAN (axial slices/reconstructions). Assess relative density (HU) when visible, evaluate per slice, "
        "and note the window (lung/mediastinum). On a single slice, report only the structures visible on that slice."
    ),
    "mri": (
        "Imaging type: MRI. Signal intensity (T1/T2/FLAIR/STIR when recognisable), not HU density; name the sequence "
        "you recognise and its limitations."
    ),
    "usg": (
        "Imaging type: ULTRASOUND. Assess echogenicity (anechoic/hypoechoic/hyperechoic), acoustic shadowing, and posterior enhancement; "
        "the field of view is sector-shaped, do not place locations outside the sector."
    ),
    "pet scan": (
        "Imaging type: PET. Assess tracer uptake pattern (hypermetabolic/photopenic) and distribution; fine size/anatomy detail is "
        "limited, mention CT correlation when needed."
    ),
}


def build_modality_block(jenis_pemeriksaan: str = "") -> str:
    key = (jenis_pemeriksaan or "").strip().lower().replace("_", "-")
    note = MODALITAS_NOTES.get(key) or MODALITAS_NOTES.get(key.replace(" ", "-")) or MODALITAS_NOTES.get(key.replace("-", " "))
    return f"\n\nIMAGING TYPE: {note}" if note else ""


def band_of_score(score: float) -> str:
    """Score 0..1 -> severity label (Low / Moderate / High)."""
    return "Low" if score < 0.34 else ("Moderate" if score < 0.67 else "High")
