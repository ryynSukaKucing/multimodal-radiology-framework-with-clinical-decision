TUJUAN_ANALISIS_FIELDS = {
    "otomatis": (
        'Choose the single most relevant module (screening/segmentation/classification/therapeutics/prognostics) '
        'according to the image findings, apply that module\'s field instructions, and fill "analysis_note" with the reason for the choice. '
        'The choice MUST be based on what is actually visible in the image, not on assumptions from the typed '
        'examination type/anatomical area; focus on the patient\'s anatomy/pathology.'
    ),
    "screening": (
        'Screening & Detection module: add a "detections" field (array of bounding boxes for initial findings, each '
        'object with "label", "score" 0..1, "box") - simulating the combined output of TorchXRayVision, '
        'Grounding DINO, YOLO-World, and CheXNet for parallel initial pathology localisation.'
    ),
    "segmentation": (
        'Segmentation & Quantitative Analysis module: add a "measurements" field (array of objects '
        '{"structure","volume_ml","area_cm2","density_hu"}) - simulating pixel segmentation by MedSAM, '
        'TotalSegmentator v2, SwinUNETR, and FastSAM-Med, followed by PyRadiomics-style quantitative feature extraction.'
    ),
    "classification": (
        'Classification & Grading module: add a "grading" field containing {"system","score","category"} '
        '(e.g. BI-RADS, Lung-RADS) - simulating tissue characterisation by BioMedCLIP, OpenCLIP-Medical, '
        'and ConvNeXt-Large into international standard scoring systems.'
    ),
    "therapeutics": (
        'Therapeutics & Decision Support module: add a "recommendations" field (array of clinical action steps) '
        'plus "urgency" (Routine/Urgent/Emergency) - simulating the action-flow recommendations produced by '
        'the local medical model BioMistral and the MedRAG reference-retrieval system.'
    ),
    "prognostics": (
        'Prognostics & Longitudinal module: add a "progression" field containing {"delta_volume_ml","trend",'
        '"recist_category"} - simulating alignment of the patient\'s historical images by SimpleITK and DeepReg, '
        'followed by volume change-rate calculation by DeepSurv, evaluated against RECIST criteria.'
    ),
}
