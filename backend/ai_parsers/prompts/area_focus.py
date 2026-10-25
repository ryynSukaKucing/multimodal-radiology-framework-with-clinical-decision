AREA_FOCUS = {
    "vaskular / koroner": (
        "Vascular/coronary angiography: identify the visible vessels (LAD, LCx, RCA & branches; or other arteries) and "
        "assess per segment: stenosis (estimated % diameter narrowing, focal/diffuse), total occlusion, filling defect/"
        "thrombus, calcification, aneurysm/ectasia, dissection, tortuosity, distal flow (estimated TIMI), collaterals. "
        "Place boxes on the narrowed/abnormal VESSEL SEGMENT (not on catheters or wires) and name the segment "
        "(proximal/mid/distal) in the label."
    ),
    "toraks / jantung-paru": (
        "Thorax: assess lung parenchyma (consolidation, nodule/mass, infiltrate, atelectasis), pleura (effusion, pneumothorax), "
        "cardiac silhouette (cardiomegaly/CTR), mediastinum, hila (enlargement/lymphadenopathy), diaphragm, ribs/clavicles. "
        "Report ALL visible abnormalities and give differential diagnoses."
    ),
    "kepala & leher": (
        "Head/neck: assess brain parenchyma (haemorrhage, infarct, mass, oedema), ventricular system & midline shift, "
        "sinuses, calvarial bones, neck structures."
    ),
    "abdomen & pelvis": (
        "Abdomen/pelvis: assess solid organs (liver, kidneys, spleen, pancreas), masses/cysts/stones, bowel gas pattern & "
        "obstruction, free fluid, pelvic bones."
    ),
    "tulang belakang": (
        "Spine: assess alignment, vertebral body & disc height, fracture/compression, listhesis, osteophytes, "
        "canal stenosis, paravertebral soft-tissue abnormalities."
    ),
    "ekstremitas": (
        "Extremities: assess cortical continuity (fracture), joint alignment/dislocation, joint space, lytic/sclerotic lesions, "
        "soft-tissue swelling."
    ),
}


# Anatomical Area as in the v5 mockup (Brain & Head-Neck, Thorax / Chest, Abdomen & Pelvis, Musculoskeletal, Breast,
# Cardiovascular, Lainnya). Kunci lama tetap dipertahankan agar riwayat/pilihan lama masih berfungsi.
AREA_FOCUS.update({
    "brain & head-neck": AREA_FOCUS["kepala & leher"],
    "thorax / chest": AREA_FOCUS["toraks / jantung-paru"],
    "musculoskeletal": AREA_FOCUS["tulang belakang"] + " " + AREA_FOCUS["ekstremitas"],
    "breast": (
        "Breast (mammography/ultrasound/MRI): assess composition/density, masses (shape, margin, density), calcifications "
        "(morphology & distribution, e.g. clustered microcalcifications), architectural distortion, asymmetry, skin thickening/"
        "nipple retraction, and axillary lymph nodes. Give a BI-RADS category when possible."
    ),
    "cardiovascular": AREA_FOCUS["vaskular / koroner"],
})


def build_area_focus(anatomical_area: str, jenis_pemeriksaan: str = "") -> str:
    key = (anatomical_area or "").strip().lower()
    focus = AREA_FOCUS.get(key, "")
    if not focus:
        return ""
    return f"\n\nCLINICAL EVALUATION GUIDE ({anatomical_area}{', ' + jenis_pemeriksaan if jenis_pemeriksaan else ''}): {focus}"
