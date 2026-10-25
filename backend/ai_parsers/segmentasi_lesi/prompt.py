"""STAGE 4 - LESION SEGMENTATION: outline (polygon) of abnormalities in 'anomalies'."""
import os
from ..contoh_loader import blok_contoh

FOLDER = os.path.dirname(__file__)

PROMPT_SEGMENTASI_LESI = (
    "LESION SEGMENTATION (stage 4): each 'anomalies' object whose edge can be determined gets \"polygon\": [[x,y],...] "
    "(8-16 points, clockwise) following the REAL boundary of the opacity/lesion in the pixels. The viewer draws the severity heatmap ONLY inside this "
    "outline, so the outline is the segmentation of the lesion. "
    "(a) The polygon encloses only the lesion area itself, NOT the whole lung or whole lobe; a focal lesion is usually <15% of the image. "
    "(b) The polygon must lie completely INSIDE the lesion's own box, and the box must be tight around the polygon. "
    "(c) The location must agree with the zone in the label: a consolidation in the 'right middle zone' lies in the middle zone, not "
    "spanning from apex to base. The polygon must lie INSIDE the lung field of the stated side (not crossing the mediastinum, bone, diaphragm, "
    "abdomen, or outside the thoracic cavity). "
    "(c2) Each lesion polygon inherits the 'lokasi_anatomi' of its object; the patient's left/right side is determined by where the polygon lies on the image "
    "(PA/AP: image-LEFT = patient RIGHT). "
    "(d) One polygon per lesion (do not join two distant lesions, and never one polygon across both lungs). "
    "(e) Diffuse lesions (massive effusion, oedema, miliary) may be larger, but must still follow the visible boundary inside the lung. "
    "(f) If the lesion edge is unclear, OMIT the polygon (box only) - better no outline than an invented one. "
    "Coordinates and 'centerline'/'keypoints' follow the general geometry rules (0..1 scale)."
)


def build_prompt(kueri: str = "", maks_contoh: int = 1) -> str:
    return PROMPT_SEGMENTASI_LESI + "\n" + blok_contoh(FOLDER, kueri, maks_contoh, "LESION SEGMENTATION EXAMPLES")
