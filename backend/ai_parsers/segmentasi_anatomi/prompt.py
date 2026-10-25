"""STAGE 3 - ANATOMICAL SEGMENTATION: outline (polygon) / line (polyline) of normal structures in 'structures'."""
import os
from ..contoh_loader import blok_contoh

FOLDER = os.path.dirname(__file__)

PROMPT_SEGMENTASI_ANATOMI = (
    "ANATOMICAL SEGMENTATION (stage 3): the geometry type follows the [shape] column of the taxonomy. [polygon] objects whose edges are clear get "
    "\"polygon\": [[x,y],...] (10-24 points, clockwise, following the REAL edge, not a generic oval/rectangle). [line] objects "
    "(diaphragm, clavicle, fissures, heart borders, aorta, vena cava) get \"polyline\": [[x,y],...] (3-12 points along the edge/line, "
    "medial to lateral or top to bottom). [box]/[point] objects need only a box. "
    "(a) 'right_lung'/'left_lung' = only the aerated lung field, from the apex (below the clavicle) to the diaphragmatic dome, bounded by the inner edge of the "
    "lateral ribs and the mediastinal border; it must not leave the thoracic cavity or cover bone, shoulder, or chest-wall "
    "soft tissue. "
    "(b) the patient's 'right_*' is on the image-LEFT, 'left_*' on the image-RIGHT; the two lung polygons must not overlap "
    "and must not cross the midline (trachea-vertebrae). "
    "(c) 'cardiac_silhouette' = the edge of the heart shadow only; 'trachea' = a narrow band on the midline; 'right_hemidiaphragm'/'left_hemidiaphragm' = "
    "the dome line (not the area beneath it). 'right_hilum'/'left_hilum' = the hilar area inside the lung near the mediastinum. "
    "(d) Lobes ('right_upper_lobe', etc.) lie INSIDE the lung of their side; fissures are the borders between lobes. "
    "(e) The polygon must match the box of the same structure (polygon inside/near its box). "
    "(f) If a structure's border is unclear, OMIT the polygon/polyline (box only) - better no outline than an invented one. "
    "(g) Lung zones need not be drawn; the system divides them from your lung outline, so the lung outline must be accurate. "
    "Token budget is limited: outlines only for priority 1; priority 2-3 need only a box."
)


def build_prompt(kueri: str = "", maks_contoh: int = 1) -> str:
    return PROMPT_SEGMENTASI_ANATOMI + "\n" + blok_contoh(FOLDER, kueri, maks_contoh, "ANATOMY SEGMENTATION EXAMPLES")
