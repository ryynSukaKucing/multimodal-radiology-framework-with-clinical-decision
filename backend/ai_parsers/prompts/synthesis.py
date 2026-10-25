def build_synthesis_block(llm_synthesis: bool = False) -> str:
    """Optional prompt block: SOAP + ICD-11 synthesis."""
    if not llm_synthesis:
        return ""
    return (
        "\n\nLLM SYNTHESIS: add a \"soap\" field containing {\"subjective\",\"objective\",\"assessment\",\"plan\"} "
        "(each a concise English string). \"subjective\" only from the supplied Clinical History (leave empty if none; "
        "do not invent complaints), \"objective\" = image findings, \"assessment\" = diagnosis & differentials, \"plan\" = follow-up suggestions. "
        "Map the diagnosis to an ICD-11 code in \"diagnosis_code\" when the code system is auto."
    )
