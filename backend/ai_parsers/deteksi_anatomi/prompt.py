"""STAGE 1 - ANATOMICAL OBJECT DETECTION: normal thoracic structures -> 'structures' (taxonomy id + box). Outlines are covered in segmentasi_anatomi."""
import os
from ..contoh_loader import blok_contoh
from ..thorax_anatomy_taxonomy import TAXA, taxonomy_prompt_block, tier_ids

FOLDER = os.path.dirname(__file__)

# Canonical id list (without lung zones, which are derived automatically).
STRUKTUR_ANATOMI_TORAKS = tuple(i for i in TAXA if TAXA[i]["group"] != "zones")

PROMPT_DETEKSI_ANATOMI = (
    "ANATOMICAL OBJECT DETECTION (stage 1, NORMAL structures): this application is dedicated to THORAX images (PA/AP/lateral chest X-ray or chest CT). "
    "Fill the \"structures\" field alongside \"anomalies\": an array of CLEARLY visible anatomical structures, each "
    "{\"id\":\"right_lung\",\"box\":{xmin,ymin,xmax,ymax},\"description\":\"brief condition\"}. "
    "\"id\" MUST be a taxonomy id (see the list); do not write free names.\n"
    + taxonomy_prompt_block() + "\n"
    "PRIORITY: (1) always try: " + ", ".join(tier_ids(1)) + ". (2) give a box when visible: " + ", ".join(tier_ids(2)) + ". "
    "(3) only when clearly visible (usually CT or a very good radiograph): " + ", ".join(tier_ids(3)) + ". "
    "One id, one object (do not repeat). Usually 12-30 objects in total; do not fill the list just because it exists in the taxonomy. "
    "Left/right means the PATIENT'S left/right: on a PA/AP projection the patient's right lung is on the LEFT side of the image ('right_*' ids on the "
    "image-left, 'left_*' ids on the image-right). The heart lies on the patient's left (image-right), the gastric air bubble below the left hemidiaphragm. "
    "Skip structures that are not visible or whose borders you cannot determine (do not invent coordinates). "
    "The 'trachea' box = a narrow box on the midline (width usually <8% of the image), not the whole mediastinum. "
    "The 'cardiac_silhouette' box = the heart shadow only, excluding the hila. The 'right_lung'/'left_lung' box = the aerated lung field "
    "only (no shoulders, chest wall, or area below the diaphragm). 'point' structures need only a small box (<6% of the image) exactly at the point. "
    "Normal structures go ONLY in 'structures', NEVER in 'anomalies'. "
    "Review order: quality & projection (PA/AP, rotation, inspiration), midline (trachea-vertebrae), right-left lung fields, hila, "
    "mediastinum, heart (CTR), diaphragm & pleural angles, bones. "
    "If the image turns out not to be a thorax, say so in 'summary' and leave 'structures' empty."
)


def build_prompt(kueri: str = "", maks_contoh: int = 2) -> str:
    return PROMPT_DETEKSI_ANATOMI + "\n" + blok_contoh(FOLDER, kueri, maks_contoh, "ANATOMY DETECTION EXAMPLES")
