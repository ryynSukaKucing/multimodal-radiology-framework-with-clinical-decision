"""STAGE 2 - LESION OBJECT DETECTION: thoracic abnormalities/pathology -> 'anomalies' (label + box + severity). Outlines are in segmentasi_lesi."""
import os
from ..contoh_loader import blok_contoh

FOLDER = os.path.dirname(__file__)

JENIS_LESI_TORAKS = (
    "consolidation/infiltrate", "nodule/mass", "pleural effusion", "pneumothorax", "atelectasis", "cardiomegaly (CTR)",
    "pulmonary oedema", "fibrosis/interstitial thickening", "calcification", "cavity", "hilar enlargement/lymphadenopathy",
    "mediastinal widening", "rib/clavicle fracture",
)

PROMPT_DETEKSI_LESI = (
    "LESION OBJECT DETECTION (stage 2, abnormalities): 'anomalies' contains only pathology that is truly visible, e.g. "
    + ", ".join(JENIS_LESI_TORAKS) + ". Normal structures MUST NOT go in 'anomalies' (that is the place of 'structures'). "
    "Each object: {\"label\":..., \"box\":{xmin,ymin,xmax,ymax}, \"severity\":..., \"description\":..., \"lokasi_anatomi\":[taxonomy ids]}. "
    "\"lokasi_anatomi\" (1-3 ids from Thorax_Anatomy_Taxonomy, e.g. [\"right_lung\",\"middle_zone_right\"], [\"left_hilum\"], "
    "[\"right_costophrenic_angle\"], [\"cardiac_silhouette\"]) MUST agree with the LOCATION OF THE BOX you draw: a lesion on the image-LEFT side "
    "(PA/AP) is on the patient's RIGHT and uses 'right_*' ids; a lesion on the image-RIGHT side uses 'left_*' ids. Zones: upper = top third of the lung, "
    "middle = middle third, lower = bottom third. The side and zone in 'label' must also match 'lokasi_anatomi'. "
    "Reading order before writing: (1) parenchyma per upper/middle/lower zone of BOTH lungs: opacity, consolidation, nodule, cavity, "
    "infiltrate, calcification, fibrosis, volume loss; (2) HILA & MEDIASTINUM: compare right vs left hilum (size, "
    "density, contour), look for hilar enlargement, paratracheal mass, mediastinal widening, do not skip them; (3) pleura (effusion, "
    "thickening, pneumothorax) and costophrenic angles; (4) heart (CTR), trachea (deviation), diaphragm, bones; "
    "(5) distribution & shape of the lesion: lobar/segmental, focal, diffuse, bilateral, perihilar, apical; homogeneous or heterogeneous. "
    "OBJECT RULES: split findings into separate objects per lesion and per type, with the zone/side in the label (e.g. 'Consolidation in the right middle "
    "zone'). One object per lesion; do not merge distant lesions into one box, and never draw one box across both lungs: a bilateral pattern becomes "
    "one object per lung, each box only on the visible opacity of that lung. The box must be TIGHT around the lesion: a box >25% of the image, or covering "
    "more than about half of a lung field, for a single focal lesion is wrong and must be shrunk. LOCATION RULES: every lung finding lies INSIDE the aerated lung "
    "field of its side, above the diaphragm dome; a pleural effusion sits at the lung base / costophrenic angle ABOVE the diaphragm, never over the abdomen or "
    "gastric bubble; hilar findings sit on the hilum, paratracheal/mediastinal findings inside the mediastinal band (not the neck or shoulders); cardiomegaly "
    "= the heart shadow only. Soft-tissue overlay, skin folds, breast or nipple shadows, ribs, clavicles, scapulae, tubes and artefacts are NOT lesions and must "
    "not be reported. Report only findings you can actually see, with the clearest ones first. Every abnormality mentioned "
    "in 'summary' or 'diagnosis' MUST have an object in 'anomalies', and conversely every 'anomalies' object must be mentioned in 'summary'. "
    "Do not create lesions that are not visible; if there is no abnormality, 'anomalies' = []. "
    "CONSISTENCY RULE (strict): every abnormality named in 'diagnosis' or 'summary' (including ones you call indeterminate, borderline, mild, low-severity or "
    "'suspected': hilar prominence, basal haziness, blunted costophrenic angle, small effusion, cardiomegaly) MUST also be an object in 'anomalies' with a box on the "
    "SAME side. Being unsure is a reason for a LOW severity_score, never a reason to leave the box out. The side in the diagnosis must equal the side where the box lies. "
    "CARDIAC SIZE: always compare the widest heart width with the internal thoracic width. If the ratio is above 0.50 report 'Cardiomegaly (CTR x.xx)' with a box on the "
    "heart shadow; never write 'heart not enlarged' unless you have compared the two widths."
)


def build_prompt(kueri: str = "", maks_contoh: int = 2) -> str:
    return PROMPT_DETEKSI_LESI + "\n" + blok_contoh(FOLDER, kueri, maks_contoh, "LESION DETECTION EXAMPLES")
