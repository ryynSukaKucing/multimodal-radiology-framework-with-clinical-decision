"""Katalog peta opsi "Area Pemindaian": 7 cabang, tiap cabang berisi sub-opsi.

Tata letak (pos) mengikuti diagram: top (atas), left1/left2 (kiri atas/bawah),
right1/right2 (kanan atas/bawah), bottom1/bottom2 (bawah kiri/kanan).
"guide" adalah arahan isi untuk AI per sub-opsi.
"""

BRANCHES = [
    {
        "key": "panduan", "label": "Patient Guidance & Instructions", "pos": "top",
        "items": [
            {"key": "restriksi_aktivitas", "label": "Activity Restriction Instructions",
             "guide": "Batasan aktivitas fisik, beban tumpu, posisi, dan durasi pembatasan yang relevan dengan temuan."},
            {"key": "persiapan_tindakan", "label": "Pre-Procedure Preparation",
             "guide": "Persiapan pasien sebelum pemeriksaan lanjutan atau tindakan: puasa, obat yang perlu dijeda atau dilanjutkan, pemeriksaan penunjang, persetujuan."},
            {"key": "manajemen_gejala", "label": "Self-Care Symptom Management",
             "guide": "Langkah perawatan mandiri di rumah untuk gejala yang berkaitan dengan temuan, dan batas kapan harus ke fasilitas kesehatan."},
            {"key": "tanda_bahaya", "label": "Emergency Warning Signs",
             "guide": "Tanda dan gejala yang menuntut pasien segera ke IGD atau menghubungi tenaga kesehatan."},
        ],
    },
    {
        "key": "diagnostik", "label": "Diagnostic Analysis & General Etiology", "pos": "left1",
        "items": [
            {"key": "diferensial", "label": "Differential Diagnosis",
             "guide": "Diagnosis banding berurutan dari yang paling mungkin, beserta fitur citra dan klinis yang mendukung atau menyingkirkan masing-masing."},
            {"key": "morfologi_lesi", "label": "Lesion Characteristics & Morphology",
             "guide": "Lokasi, ukuran relatif, batas, densitas atau intensitas sinyal, pola, dan efek desak ruang berdasarkan deskripsi temuan."},
            {"key": "invasi_jaringan", "label": "Invasion Prediction & Tissue Involvement",
             "guide": "Struktur sekitar yang mungkin terlibat atau terancam, dan pemeriksaan yang diperlukan untuk memastikannya."},
        ],
    },
    {
        "key": "prognosis", "label": "Prognosis & Recovery Estimate", "pos": "left2",
        "items": [
            {"key": "stratifikasi", "label": "Clinical Severity Stratification",
             "guide": "Tingkat keparahan (ringan, sedang, berat, kritis) dengan alasan dan skala klinis yang lazim dipakai bila ada."},
            {"key": "timeline_pemulihan", "label": "Estimated Recovery Timeline",
             "guide": "Perkiraan fase dan rentang waktu pemulihan dengan asumsi yang disebutkan. Nyatakan ketidakpastiannya."},
            {"key": "risiko_komplikasi", "label": "Complication Risk Indicators",
             "guide": "Komplikasi yang mungkin terjadi, faktor yang meningkatkan risikonya pada pasien ini, dan indikator pemantauannya."},
        ],
    },
    {
        "key": "farmakologi", "label": "Pharmacology & Drug Response", "pos": "right1",
        "items": [
            {"key": "sensitivitas_obat", "label": "Drug Regimen Sensitivity",
             "guide": "Golongan obat atau regimen yang lazim dipertimbangkan untuk kondisi ini dan faktor pasien yang mempengaruhi responnya."},
            {"key": "toksisitas", "label": "Toxicity & Side Effect Prediction",
             "guide": "Efek samping atau toksisitas yang perlu diantisipasi, terutama terkait fungsi ginjal, hati, jantung, dan komorbid pasien."},
            {"key": "proteksi_organ", "label": "Organ Protection Recommendations",
             "guide": "Langkah proteksi organ, penyesuaian dosis, dan pemantauan laboratorium yang disarankan."},
        ],
    },
    {
        "key": "risiko", "label": "Risk Factor & Causality Profile", "pos": "right2",
        "items": [
            {"key": "risiko_komorbid", "label": "Comorbid & Systemic Factors",
             "guide": "Komorbid dan kondisi sistemik pasien yang berperan sebagai faktor risiko atau pemberat temuan ini."},
            {"key": "paparan_trauma", "label": "Exposure & Trauma History",
             "guide": "Paparan lingkungan, kebiasaan, radiasi, obat, atau trauma yang mungkin berhubungan. Tulis 'belum ada data' bila tidak tercatat."},
            {"key": "predisposisi", "label": "Demographic & Anatomical Predisposition",
             "guide": "Usia, jenis kelamin, genetik, dan variasi anatomi yang mempengaruhi kecenderungan terjadinya temuan."},
        ],
    },
    {
        "key": "pemberat", "label": "Events & Aggravating Factors", "pos": "bottom1",
        "items": [
            {"key": "kegagalan_struktural", "label": "Structural Failure / Rupture Risk",
             "guide": "Risiko fraktur patologis, ruptur, herniasi, atau kegagalan struktur lain terkait temuan, dan tanda peringatannya."},
            {"key": "pemberat_komorbid", "label": "Comorbid & Systemic Factors",
             "guide": "Kondisi sistemik yang memperberat perjalanan temuan atau menghambat penyembuhan pada pasien ini."},
            {"key": "inflamasi_infeksi", "label": "Signs of Acute Inflammation & Infection",
             "guide": "Tanda inflamasi atau infeksi yang terlihat atau perlu dicari, serta pemeriksaan penanda yang relevan."},
        ],
    },
    {
        "key": "terapi", "label": "Therapy Types & Medical Interventions", "pos": "bottom2",
        "items": [
            {"key": "terapi_utama", "label": "Primary Therapy Options",
             "guide": "Opsi terapi utama (medikamentosa, bedah, radioterapi, dll.) yang lazim untuk kondisi ini, dengan pertimbangan kondisi pasien."},
            {"key": "protokol_kombinasi", "label": "Combination Protocols",
             "guide": "Kombinasi modalitas terapi, urutan, dan syarat kelayakan pasien untuk masing-masing."},
            {"key": "intervensi_minimal", "label": "Minimally Invasive Intervention Options",
             "guide": "Prosedur minimal invasif atau perkutan yang mungkin menjadi alternatif, beserta indikasi dan kontraindikasinya."},
            {"key": "terapi_suportif", "label": "Supportive Therapy Plan",
             "guide": "Terapi suportif: nyeri, nutrisi, rehabilitasi, psikososial, dan perawatan paliatif bila relevan."},
        ],
    },
]

_ORDER = ["diagnostik", "risiko", "pemberat", "terapi", "farmakologi", "prognosis", "panduan"]
BRANCHES.sort(key=lambda b: _ORDER.index(b["key"]))
for _i, _b in enumerate(BRANCHES):
    _b["pos"] = f"s{_i + 1}"
for _b in BRANCHES:
    if _b["key"] == "farmakologi":
        _b["label"] = "Pharmacology & Drug Response"

BRANCH_BY_KEY = {b["key"]: b for b in BRANCHES}


def public_catalog():
    """Versi tanpa 'guide' untuk frontend."""
    return [
        {
            "key": b["key"], "label": b["label"], "pos": b["pos"],
            "items": [{"key": i["key"], "label": i["label"]} for i in b["items"]],
        }
        for b in BRANCHES
    ]
