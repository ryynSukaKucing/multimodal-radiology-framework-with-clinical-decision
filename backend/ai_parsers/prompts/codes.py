DIAGNOSIS_CODE_INSTRUCTIONS = {
    "auto": 'Automatically choose the most suitable code system (clinical: ICD-10/ICD-11/SNOMED CT, or nursing: SDKI/NANDA-I when the finding is a nursing problem) and put it in the "diagnosis_code" & "diagnosis_code_system" fields.',
    "icd10": 'Use ICD-10. If the diagnosis is still a suspicion from imaging (not confirmed by laboratory/histology), choose an unconfirmed/unspecified category code when available. Fill "diagnosis_code" as "ICD-10 <code> <name>", e.g. "ICD-10 I25.82 Chronic total occlusion of coronary artery".',
    "icd11": 'Use ICD-11. Fill "diagnosis_code" as "ICD-11 <code> <name>", e.g. "ICD-11 BA81.2 Chronic total occlusion of coronary artery".',
    "snomed": 'Use SNOMED CT. Fill "diagnosis_code" as "SNOMED CT <code> <name> (disorder)", e.g. "SNOMED CT 413444003 Complete occlusion of coronary artery (disorder)".',
    "sdki": 'Use SDKI (Indonesian Nursing Diagnosis Standard). Fill "diagnosis_code" as "SDKI <code> <name>", e.g. "SDKI D.0008 Decreased Cardiac Output".',
    "nanda": 'Use NANDA-I. Fill "diagnosis_code" as "NANDA-I <code> <name>", e.g. "NANDA-I 00029 Decreased Cardiac Output".',
}
