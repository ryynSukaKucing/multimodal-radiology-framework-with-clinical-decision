from typing import Optional
from .base import get_system_prompt
from .modules import TUJUAN_ANALISIS_FIELDS
from .area_focus import build_area_focus
from .. import deteksi_anatomi, deteksi_lesi, segmentasi_anatomi, segmentasi_lesi, diagnosa_medis
from ..thorax_anatomy_taxonomy import taxonomy_prompt_block
from .codes import DIAGNOSIS_CODE_INSTRUCTIONS
from .geometry_notes import VISUAL_GEOMETRY_NOTE, VISUAL_GEOMETRY_NOTE_DETECT, build_image_scale_note
from .modes import (MODE_ANATOMI_LESI, MODE_INSTRUCTIONS, MODE_INSTRUCTIONS_DETECT, DETECT_ONLY_NOTE, SEVERITY_SCORE_PROMPT, build_modality_block,
                    mode_has_anatomy, mode_has_lesion, normalize_mode)


def build_dynamic_system_prompt(
    model_lower: str,
    tujuan_analisis: str = "otomatis",
    diagnosis_code_system: str = "auto",
    scan_meta: Optional[dict] = None,
    clinical_context: str = "",
    synthesis_block: str = "",
    img_wh=None,
    mode_pindai: str = MODE_ANATOMI_LESI,
    fov=None,
    stage: str = "full",
) -> str:
    """Menyusun system prompt final untuk model AI (API): dasar (skema JSON umum) + instruksi modul
    Tujuan Analisis + instruksi sistem kode diagnosis + konteks klinis pasien (Clinical History),
    tanpa mengubah skema dasar (diagnosis/confidence/summary/anomalies) agar kompatibel dengan renderer.

    stage="full"   : empat tahap sekaligus (deteksi + segmentasi), perilaku lama.
    stage="detect" : panggilan 1 dari 2, hanya deteksi objek (kotak) + diagnosis; kontur diminta terpisah (lihat segmentasi_tahap.py)."""
    base = get_system_prompt(model_lower)
    mode = normalize_mode(mode_pindai)
    tujuan_key = (tujuan_analisis or "otomatis").lower()
    code_key = (diagnosis_code_system or "auto").lower()

    extra_fields = TUJUAN_ANALISIS_FIELDS.get(tujuan_key, TUJUAN_ANALISIS_FIELDS["otomatis"])
    code_instruction = DIAGNOSIS_CODE_INSTRUCTIONS.get(code_key, DIAGNOSIS_CODE_INSTRUCTIONS["auto"])

    meta_lines = []
    if scan_meta:
        for k, v in scan_meta.items():
            if v:
                meta_lines.append(f"- {k}: {v}")
    area_block = build_area_focus((scan_meta or {}).get("Anatomical Area", ""), (scan_meta or {}).get("Examination Type", ""))
    meta_block = ("\n\nScan metadata:\n" + "\n".join(meta_lines)) if meta_lines else ""

    ctx_block = f"\n\nPatient Clinical History context (use as additional data, do not repeat verbatim):\n{clinical_context.strip()}" if clinical_context and clinical_context.strip() else ""

    kueri = " ".join(filter(None, [(scan_meta or {}).get("Anatomical Area", ""), (scan_meta or {}).get("Examination Type", ""), clinical_context or ""]))

    # Stages 1-4 are included per scan mode (anatomy: 1+3, lesions: 2+4, both: all).
    detect_only = (stage == "detect")
    stage_parts = []
    if mode_has_anatomy(mode):
        stage_parts.append(deteksi_anatomi.build_prompt(kueri))
        if not detect_only:
            stage_parts.append(segmentasi_anatomi.build_prompt(kueri))
    if mode_has_lesion(mode) and not mode_has_anatomy(mode):
        stage_parts.append("ANATOMICAL LOCATION ID REFERENCE (only for filling 'lokasi_anatomi' on lesions; 'structures' stays empty):\n"
                           + taxonomy_prompt_block())
    if mode_has_lesion(mode):
        stage_parts.append(deteksi_lesi.build_prompt(kueri))
        if not detect_only:
            stage_parts.append(segmentasi_lesi.build_prompt(kueri))
        stage_parts.append(SEVERITY_SCORE_PROMPT)
    stage_block = "".join(p + "\n\n" for p in stage_parts)
    geometry_note = VISUAL_GEOMETRY_NOTE_DETECT if detect_only else VISUAL_GEOMETRY_NOTE
    mode_note = (MODE_INSTRUCTIONS_DETECT if detect_only else MODE_INSTRUCTIONS)[mode]
    detect_note = f"{DETECT_ONLY_NOTE}\n\n" if detect_only else ""

    return (
        f"{base}\n\n"
        f"ANALYSIS GOAL MODULE INSTRUCTIONS ({tujuan_key}): {extra_fields}\n\n"
        f"DIAGNOSIS CODE INSTRUCTIONS: {code_instruction}\n\n"
        f"{geometry_note}{build_image_scale_note(img_wh, fov)}\n\n"
        f"{mode_note}\n\n"
        f"{detect_note}"
        f"{stage_block}"
        f"{diagnosa_medis.build_prompt(kueri)}\n\n"
        f"The additional fields above (\"structures\"/\"analysis_note\"/\"detections\"/\"measurements\"/\"grading\"/\"recommendations\"/"
        f"\"progression\"/\"diagnosis_code\"/\"diagnosis_code_system\") are added INSIDE the same JSON object, "
        f"alongside \"diagnosis\", \"confidence\", \"summary\", \"anomalies\". Also include the field "
        f"\"diagnosis_alternatif\" (array of strings, possible differential diagnoses, may be empty) "
        f"alongside \"diagnosis\". All free-text values MUST be in English. Reply with the JSON object ONLY."
        f"{area_block}{build_modality_block((scan_meta or {}).get('Examination Type', ''))}{meta_block}{ctx_block}{synthesis_block}"
    )
