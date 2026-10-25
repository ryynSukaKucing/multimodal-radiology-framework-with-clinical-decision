"""Paket ai_parsers (sebelumnya satu file ai_parsers.py).

Semua nama lama diimpor ulang di sini, jadi `import ai_parsers` tetap bekerja.
Urutan dependensi satu arah: common -> thorax_anatomy_taxonomy -> text_extract -> json_repair -> geometry -> normalize.
thorax_anatomy_taxonomy (Thorax_Anatomy_Taxonomy) adalah sumber tunggal id/label/warna anatomi toraks; geo_utils = fungsi geometri 2D.
prompts/ mandiri (tidak mengimpor parser); prompts/builder.py merakit prompt dari lima folder tahap:
deteksi_anatomi, deteksi_lesi, segmentasi_anatomi, segmentasi_lesi, diagnosa_medis (masing-masing: prompt.py + contoh.jsonl).
"""
from .common import (EXPECTED_KEYS, _num, _as_text)
from .text_extract import (_THINK_CLOSED_RE, _THINK_OPEN_RE, _FENCE_RE, extract_text, extract_message_text, _strip_reasoning)
from .json_repair import (_iter_json_objects, _json5_lite, repair_truncated_json, _try_load, _score_obj, parse_with_mode)
from .thorax_anatomy_taxonomy import (THORAX_ANATOMY_TAXONOMY, TAXA, SYSTEM_LABEL, GROUP_LABEL, resolve_taxon, taxonomy_prompt_block, label_of)
from .geometry import (_COORD_1000_FAMILIES, _scale_box, _norm_box, _POLY_KEYS, _norm_points, _poly_of, _box_from_poly, normalize_structures, _clamp01, _clean_points, sanitize_anomaly_geometry, sanitize_structures)
from .normalize import (_SEV_MAP, _ALIASES, _unwrap, _to_float01, _norm_severity, normalize_result, text_fallback_result, parse_model_response)
from .devices import (DEVICE_KEYWORDS, DEVICE_ALLOW, strip_device_findings, strip_nonlesion_findings)
from .prompts.base import (ANTI_HALUSINASI_NOTE, SYSTEM_PROMPT_HAIKU, SYSTEM_PROMPT_CLAUDE, SYSTEM_PROMPT_GENERIC, get_system_prompt)
from .prompts.modules import (TUJUAN_ANALISIS_FIELDS)
from .prompts.area_focus import (AREA_FOCUS, build_area_focus)
from .prompts.codes import (DIAGNOSIS_CODE_INSTRUCTIONS)
from .prompts.geometry_notes import (VISUAL_GEOMETRY_NOTE, build_image_scale_note)
from .prompts.synthesis import (build_synthesis_block)
from .prompts.repair import (REPAIR_PROMPT, repair_refused)
from .prompts.modes import (MODE_VALID, MODE_LABEL, MODE_ANATOMI, MODE_LESI, MODE_ANATOMI_LESI, normalize_mode, mode_has_anatomy, mode_has_lesion, band_of_score, build_modality_block, SEVERITY_SCORE_PROMPT)
from .prompts.builder import (build_dynamic_system_prompt)
from .contoh_loader import (baca_contoh, blok_contoh)
from .deteksi_anatomi import (STRUKTUR_ANATOMI_TORAKS, PROMPT_DETEKSI_ANATOMI)
from .deteksi_lesi import (JENIS_LESI_TORAKS, PROMPT_DETEKSI_LESI)
from .segmentasi_anatomi import (PROMPT_SEGMENTASI_ANATOMI, fix_laterality, reconcile_structures, reconcile_structures_ex, derive_zones)
from .segmentasi_lesi import (PROMPT_SEGMENTASI_LESI, refine_anomaly_geometry, align_text_laterality, swap_side_words)
from .diagnosa_medis import (PROMPT_DIAGNOSA_MEDIS, reconcile_thorax_diagnosis, sync_diagnosis_with_findings, describe_findings)
THORAX_STRUCTURE_LABELS = STRUKTUR_ANATOMI_TORAKS  # alias nama lama
from .grounding import (find_ungrounded, build_grounding_prompt, parse_grounding, compute_ctr, apply_ctr, merge_grounded, lung_structures, run_grounding_pass, has_cardiomegaly_lesion)
from .segmentasi_tahap import (SEGMENTATION_MARK, pick_lesions, pick_structures, build_segmentation_prompt, parse_segmentation_json, extract_outlines, merge_outlines, is_segmented)
from .prompts.modes import (MODE_INSTRUCTIONS_DETECT, DETECT_ONLY_NOTE)
