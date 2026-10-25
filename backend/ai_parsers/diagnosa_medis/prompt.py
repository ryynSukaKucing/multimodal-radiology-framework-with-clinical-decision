"""STAGE 5 - MEDICAL DIAGNOSIS: findings (anatomy + lesions) -> main diagnosis, differentials, confidence, confirmation advice."""
import os
from ..contoh_loader import blok_contoh

FOLDER = os.path.dirname(__file__)

PROMPT_DIAGNOSA_MEDIS = (
    "MEDICAL DIAGNOSIS (stage 5, general, not biased toward one disease): first describe the PATTERN of the findings from the detection stages, then "
    "choose the best-fitting diagnosis and write 2-3 differential diagnoses in 'diagnosis_alternatif'. Pattern guide: "
    "homogeneous CONSOLIDATION filling one lobe/segment with air bronchogram -> lobar pneumonia; heterogeneous/"
    "multifocal/perihilar consolidation, or with cavitation, satellite nodules, apical lesion, fibrosis, miliary pattern, or hilar/paratracheal enlargement "
    "-> consider granulomatous infection (e.g. TB) and malignancy; "
    "solitary MASS/NODULE, spiculation, thick-walled cavity, enlarged hilum/mediastinum -> malignancy vs infection; "
    "bilateral perihilar 'butterfly' OPACITY + cardiomegaly + Kerley lines/effusion -> cardiogenic pulmonary oedema; "
    "homogeneous basal OPACITY with meniscus and blunted costophrenic angle -> pleural effusion; "
    "hyperlucent area without lung markings + pleural line -> pneumothorax; "
    "opacity with traction of the trachea/hilum/fissure/diaphragm toward the lesion side -> atelectasis/volume loss; "
    "heart CTR >0.5 (PA) -> cardiomegaly. "
    "RULES: do not name a specific diagnosis just because of a single finding (e.g. 'consolidation' is not necessarily 'lobar pneumonia'); "
    "the diagnosis must be supported by ALL reported findings in 'anomalies' (and ONLY by them: never name a disease whose key finding has no object in 'anomalies'), and findings that do not fit the main diagnosis must be explained "
    "or the diagnosis replaced. If the findings are atypical, write a descriptive diagnosis (e.g. 'Right middle zone consolidation with "
    "right hilar enlargement') and rank the differentials. "
    "CONFIDENCE CALIBRATION: a single radiographic projection rarely justifies >0.85; when an equally plausible differential exists, 'confidence' is at most 0.75. "
    "A chest X-ray cannot establish the aetiology (infection/malignancy): suggest appropriate confirmatory tests in 'summary'. "
    "If the diagnosis is still a suspicion from imaging, write it as 'suspected', not as certainty."
)


def build_prompt(kueri: str = "", maks_contoh: int = 2) -> str:
    return PROMPT_DIAGNOSA_MEDIS + "\n" + blok_contoh(FOLDER, kueri, maks_contoh, "DIAGNOSIS EXAMPLES")
