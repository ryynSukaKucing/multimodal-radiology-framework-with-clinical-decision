"""Uji parser JSON robust. Jalankan: python -m pytest tests -q   (atau: python tests/test_ai_parsers.py)"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ai_parsers as P

GOOD = {"diagnosis": "Stenosis LAD proksimal", "confidence": 0.82, "summary": "Penyempitan fokal.",
        "anomalies": [{"id": "l1", "label": "Stenosis", "severity": "Tinggi", "description": "LAD",
                       "box": {"xmin": .2, "ymin": .3, "xmax": .4, "ymax": .5}}]}
G = json.dumps(GOOD, ensure_ascii=False)

CASES = {
    "bersih": G,
    "pagar markdown + pengantar": "Berikut hasilnya:\n```json\n" + G + "\n```\nSemoga membantu {ya}.",
    "think tertutup berisi kurung": "<think>Saya pikir {x} lalu {\"a\":1}. Hmm.</think>\n" + G,
    "think tak ditutup + json": "<think>mikir {", 
    "list part": [{"type": "text", "text": G}],
    "kutip tunggal python": "{'diagnosis': 'Stenosis LAD', 'confidence': 0.8, 'summary': 'ok', 'anomalies': [], 'x': None, 'y': True}",
    "key tanpa kutip + komentar": '{diagnosis: "Stenosis LAD", // utama\n confidence: 0.8, summary: "ok", anomalies: [] /* kosong */}',
    "trailing comma": '{"diagnosis": "A", "confidence": 0.5, "summary": "s", "anomalies": [{"label":"x","severity":"Rendah",},],}',
    "kutip dalam string": '{"diagnosis": "Stenosis "tinggi" pada LAD", "confidence": 0.7, "summary": "a", "anomalies": []}',
    "newline mentah dalam string": '{"diagnosis": "A", "confidence": 0.7, "summary": "baris1\nbaris2", "anomalies": []}',
    "koma hilang": '{"diagnosis": "A" "confidence": 0.7 "summary": "s" "anomalies": []}',
    "terpotong": G[:-40],
    "terpotong di tengah string": '{"diagnosis": "A", "confidence": 0.7, "summary": "teks yang terpo',
    "terpotong setelah colon": '{"diagnosis": "A", "confidence": 0.7, "summary":',
    "dibungkus result": json.dumps({"result": GOOD}),
    "dua objek, ambil yang benar": '{"contoh": 1} lalu ' + G,
    "kurung liar sebelum json": "Catatan { tidak seimbang. " + G,
}

def run():
    fails = 0
    for name, raw in CASES.items():
        obj, mode = P.parse_with_mode(raw)
        if name == "think tak ditutup + json":
            ok = obj is None
        else:
            ok = isinstance(obj, dict) and P.normalize_result(obj)["diagnosis"] not in ("", "Tidak Teridentifikasi")
        print(("OK  " if ok else "GAGAL"), f"{name:34s} mode={mode}")
        fails += 0 if ok else 1
    # normalisasi
    n = P.normalize_result({"Diagnosis": "X", "confidence": "85%", "anomalies": {"label": "a", "severity": "high", "bbox": [10, 20, 40, 60]}})
    assert n["confidence"] == 0.85 and n["anomalies"][0]["severity"] == "High", n
    assert abs(n["anomalies"][0]["box"]["xmax"] - 0.4) < 1e-9, n
    g = P.normalize_result({"diagnosis": "X", "anomalies": [{"label": "a", "box_2d": [100, 200, 300, 400]}]})
    assert g["anomalies"][0]["box"] == {"xmin": .2, "ymin": .1, "xmax": .4, "ymax": .3}, g
    px = P.normalize_result({"diagnosis": "X", "anomalies": [{"label": "a", "box": {"xmin": 512, "ymin": 256, "xmax": 1024, "ymax": 768}}]}, img_wh=(2048, 1536))
    assert abs(px["anomalies"][0]["box"]["xmin"] - .25) < 1e-9, px
    assert P.extract_message_text({"content": None, "reasoning_content": "x " + G})
    assert P.text_fallback_result("Hanya prosa tanpa json")["parse_mode"] == "text_fallback"
    assert P.parse_model_response("x", "tidak ada json") is None
    print("normalisasi OK; gagal =", fails)
    return fails

def run_thorax():
    # 1) pneumonia lobaris + temuan atipikal -> diagnosis utama TETAP, banding ditambah, keyakinan dibatasi
    r = {"diagnosis": "Pneumonia Lobaris Paru Kanan", "confidence": 0.92, "diagnosis_alternatif": [],
         "summary": "Konsolidasi zona tengah paru kanan disertai pelebaran hilus kanan.",
         "anomalies": [{"label": "Konsolidasi", "description": "zona tengah paru kanan"},
                       {"label": "Limfadenopati hilus kanan", "description": "hilus melebar"}]}
    r, note = P.reconcile_thorax_diagnosis(r)
    assert r["diagnosis"] == "Pneumonia Lobaris Paru Kanan", r
    assert r["confidence"] <= 0.75 and any("ranulomatous" in a for a in r["diagnosis_alternatif"]), r
    # 2) pneumonia lobaris murni (hilus normal, dinyatakan negatif) -> tidak diubah
    r2 = {"diagnosis": "Pneumonia Lobaris Lobus Bawah Kanan", "confidence": 0.78, "diagnosis_alternatif": ["Atelektasis"],
          "summary": "Konsolidasi homogen lobus bawah kanan dengan air bronchogram. Tidak ada limfadenopati hilus, tanpa kavitas.",
          "anomalies": [{"label": "Konsolidasi", "description": "lobus bawah kanan"}]}
    r2, note2 = P.reconcile_thorax_diagnosis(r2)
    assert r2["diagnosis"].startswith("Pneumonia Lobaris") and note2 is None and r2["confidence"] == 0.78, r2
    # 2b) diagnosis non-pneumonia (efusi) tidak disentuh sama sekali
    r3 = {"diagnosis": "Efusi Pleura Kiri", "confidence": 0.7, "diagnosis_alternatif": ["Atelektasis basal"],
          "summary": "Opasitas basal kiri dengan meniskus.", "anomalies": []}
    r3, note3 = P.reconcile_thorax_diagnosis(r3)
    assert r3["diagnosis"] == "Efusi Pleura Kiri" and note3 is None, r3
    # 3) kiri/kanan tertukar: TANPA landmark garis tengah label dibiarkan (hanya diberi peringatan); DENGAN landmark dibalik
    st = [{"label": "Paru kanan", "box": {"xmin": .55, "xmax": .95, "ymin": .1, "ymax": .8}},
          {"label": "Paru kiri", "box": {"xmin": .05, "xmax": .45, "ymin": .1, "ymax": .8}}]
    nts = P.fix_laterality(st)
    assert st[0]["label"] == "Right lung" and st[1]["label"] == "Left lung" and st[0].get("lateralitas_tidak_pasti"), st
    assert any("NOT applied" in x for x in nts), nts
    st = [{"label": "Paru kanan", "box": {"xmin": .55, "xmax": .95, "ymin": .1, "ymax": .8}},
          {"label": "Paru kiri", "box": {"xmin": .05, "xmax": .45, "ymin": .1, "ymax": .8}},
          {"id": "trachea", "box": {"xmin": .47, "xmax": .53, "ymin": .05, "ymax": .3}}]
    P.fix_laterality(st)
    assert st[0]["label"] == "Left lung" and st[1]["label"] == "Right lung", st
    # 4) kontur konsolidasi dijepit ke dalam paru kanan
    st2 = [{"label": "Paru kanan", "box": {"xmin": .05, "xmax": .45, "ymin": .1, "ymax": .8}}]
    an = [{"label": "Konsolidasi paru kanan", "box": {"xmin": .0, "ymin": .3, "xmax": .6, "ymax": .5},
           "polygon": [[0.0, .3], [.6, .3], [.6, .5], [0.0, .5]]}]
    P.refine_anomaly_geometry(an, st2)
    assert an[0]["box"]["xmin"] == .05 and an[0]["box"]["xmax"] == .45, an
    # 5) prompt memuat protokol TB dan aturan kontur
    sp = P.build_dynamic_system_prompt("gemini", scan_meta={"Anatomical Area": "Thorax / Chest"}, img_wh=(1024, 1024))
    for kunci in ("ANATOMICAL OBJECT DETECTION", "LESION OBJECT DETECTION", "ANATOMICAL SEGMENTATION", "LESION SEGMENTATION", "MEDICAL DIAGNOSIS"):
        assert kunci in sp, kunci
    assert "TB PRIMER" not in sp
    # few-shot dari contoh.jsonl ikut tersisip, dan baris berstatus ai_draft/rejected tidak pernah dipakai
    assert "DIAGNOSIS EXAMPLES" in sp
    import tempfile, json, os as _os
    with tempfile.TemporaryDirectory() as d:
        open(_os.path.join(d, "contoh.jsonl"), "w", encoding="utf-8").write(
            json.dumps({"prompt": "a b c", "jawaban": "X", "status": "ai_draft"}) + "\n"
            + json.dumps({"prompt": "konsolidasi paru", "jawaban": "Y", "status": "verified"}) + "\n")
        blk = P.blok_contoh(d, "konsolidasi")
        assert "Output: Y" in blk and "Output: X" not in blk, blk
    print("thorax OK")
    return 0

def run_mode_dan_keparahan():
    # mode pindai: normalisasi nilai form
    assert P.normalize_mode("anatomi") == "anatomi" and P.normalize_mode("lesi") == "lesi"
    assert P.normalize_mode("Anatomi + Lesi") == "anatomi_lesi" and P.normalize_mode("") == "anatomi_lesi"
    # prompt hanya memuat tahap sesuai mode
    meta = {"Anatomical Area": "Thorax / Chest", "Examination Type": "CT-Scan"}
    pa = P.build_dynamic_system_prompt("claude", scan_meta=meta, mode_pindai="anatomi")
    pl = P.build_dynamic_system_prompt("claude", scan_meta=meta, mode_pindai="lesi")
    pb = P.build_dynamic_system_prompt("claude", scan_meta=meta, mode_pindai="anatomi_lesi")
    assert "ANATOMICAL OBJECT DETECTION" in pa and "ANATOMICAL SEGMENTATION" in pa and "LESION OBJECT DETECTION" not in pa and "SEVERITY PARAMETER" not in pa
    assert "LESION OBJECT DETECTION" in pl and "LESION SEGMENTATION" in pl and "ANATOMICAL OBJECT DETECTION" not in pl and "SEVERITY PARAMETER" in pl
    assert all(k in pb for k in ("ANATOMICAL OBJECT DETECTION", "LESION OBJECT DETECTION", "ANATOMICAL SEGMENTATION", "LESION SEGMENTATION", "SEVERITY PARAMETER"))
    assert "CT-SCAN" in pb and "SCAN MODE = ANATOMY + LESIONS" in pb
    # skor keparahan: dari model (0..1, persen, string) atau diturunkan dari label; label dibuat konsisten dengan skor
    n = P.normalize_result({"diagnosis": "X", "anomalies": [
        {"label": "a", "severity": "Rendah", "severity_score": 0.9},
        {"label": "b", "severity": "Tinggi"},
        {"label": "c", "severity": "Sedang", "severity_score": "58%"},
        {"label": "d", "severity": "Rendah", "derajat_keparahan": 12},
        {"label": "e"}]})
    a = {x["label"]: x for x in n["anomalies"]}
    assert a["a"]["severity_score"] == 0.9 and a["a"]["severity"] == "High" and a["a"]["severity_score_source"] == "model"
    assert a["b"]["severity_score"] == 0.82 and a["b"]["severity_score_source"] == "derived"
    assert a["c"]["severity_score"] == 0.58 and a["c"]["severity"] == "Moderate"
    assert a["d"]["severity_score"] == 0.12 and a["d"]["severity"] == "Low"
    assert 0.0 <= a["e"]["severity_score"] <= 1.0
    assert P.band_of_score(0.33) == "Low" and P.band_of_score(0.34) == "Moderate" and P.band_of_score(0.67) == "High"
    print("mode + keparahan OK")
    return 0

def test_mode_dan_keparahan():
    assert run_mode_dan_keparahan() == 0

def test_thorax():
    assert run_thorax() == 0

def test_parsers():
    assert run() == 0

def _pa_model_output(flipped=False):
    """Keluaran model tiruan untuk rontgen PA: lapang paru, hilus, jantung, diafragma dengan koordinat NYATA (kanan pasien = kiri gambar).
    flipped=True meniru model yang memakai konvensi gambar (menamai sisi kiri gambar sebagai 'kiri')."""
    R, L = ("Paru kanan", "Paru kiri") if not flipped else ("Paru kiri", "Paru kanan")
    hR, hL = ("Hilus kanan", "Hilus kiri") if not flipped else ("Hilus kiri", "Hilus kanan")
    dR, dL = ("right_hemidiaphragm", "left_hemidiaphragm") if not flipped else ("left_hemidiaphragm", "right_hemidiaphragm")
    return {
        "diagnosis": "Right lobar pneumonia" if not flipped else "Left lobar pneumonia", "confidence": 0.7,
        "summary": ("Consolidation in the right middle zone." if not flipped else "Consolidation in the left middle zone."),
        "structures": [
            {"label": R, "polygon": [[.12, .15], [.3, .13], [.45, .25], [.46, .6], [.4, .82], [.2, .84], [.1, .6]]},
            {"label": L, "polygon": [[.56, .15], [.72, .13], [.88, .2], [.9, .6], [.85, .82], [.62, .84], [.55, .6]]},
            {"label": hR, "box": {"xmin": .34, "ymin": .3, "xmax": .46, "ymax": .5}},
            {"label": hL, "box": {"xmin": .54, "ymin": .28, "xmax": .66, "ymax": .48}},
            {"id": "cardiac_silhouette", "box": {"xmin": .38, "ymin": .55, "xmax": .7, "ymax": .88}},
            {"id": "trachea", "box": {"xmin": .47, "ymin": .05, "xmax": .53, "ymax": .3}},
            {"id": dR, "box": {"xmin": .1, "ymin": .8, "xmax": .46, "ymax": .9}, "polyline": [[.1, .86], [.25, .8], [.46, .85]]},
            {"id": dL, "box": {"xmin": .54, "ymin": .82, "xmax": .9, "ymax": .92}},
            {"label": "Kateter vena sentral", "box": {"xmin": .5, "ymin": .1, "xmax": .52, "ymax": .5}},
        ],
        "anomalies": [
            {"label": "Consolidation in the right middle zone" if not flipped else "Consolidation in the left middle zone",
             "box": {"xmin": .15, "ymin": .4, "xmax": .35, "ymax": .6}, "severity": "Sedang",
             "description": "airspace opacity in the right lung" if not flipped else "airspace opacity in the left lung"},
        ],
    }


def run_taksonomi():
    import ai_parsers.thorax_anatomy_taxonomy as T
    # 1) taksonomi: setiap id daun ada di registri dan resolver membaca id, nama Indonesia, Inggris, dan alias lama
    assert len(T.TAXA) >= 54 and T.resolve_taxon("Arkus aorta") == "aortic_knob" and T.resolve_taxon("Left Lung") == "left_lung"
    assert T.resolve_taxon("Pembuluh paru") is None and T.resolve_taxon("Kateter") is None
    assert T.resolve_taxon("Paru kanan zona atas paru kiri", "R") == "upper_zone_right"     # label kacau diputuskan dari posisi
    # 2) keluaran benar: id baku, zona diturunkan, kateter (di luar taksonomi) dibuang, label baku Indonesia
    n = P.normalize_result(_pa_model_output(False))
    ids = [s["taxon"] for s in n["structures"]]
    assert "right_lung" in ids and "left_hilum" in ids and "cardiac_silhouette" in ids and not any("kateter" in s["label"].lower() for s in n["structures"]), ids
    assert any("taxonomy" in x for x in n["_struct_notes"]), n["_struct_notes"]
    st, notes = P.reconcile_structures(n["structures"])
    by = {s["taxon"]: s for s in st}
    assert by["right_lung"]["label"] == "Right lung" and by["right_lung"]["color"].startswith("#")
    assert {"middle_zone_right", "lower_zone_left", "apex_left"} <= set(by) and by["middle_zone_right"]["derived"] is True
    assert by["right_hemidiaphragm"]["polyline"] and by["right_hemidiaphragm"]["geom"] == "line"
    # 3) model terbalik (konvensi gambar): seluruh label sisi dibalik, lesi + ringkasan + diagnosis ikut konsisten
    f = P.normalize_result(_pa_model_output(True))
    st, notes = P.reconcile_structures(f["structures"])
    by = {s["taxon"]: s for s in st}
    assert by["right_lung"]["box"]["xmax"] < .5 < by["left_lung"]["box"]["xmin"], notes
    assert by["right_hilum"]["box"]["xmax"] < .5 and by["left_hemidiaphragm"]["box"]["xmin"] > .5, notes
    assert any("reversed" in x for x in notes), notes
    an = f["anomalies"]
    P.refine_anomaly_geometry(an, st)
    assert an[0]["koreksi_lateralitas"] and "right" in an[0]["label"].lower() and "left" not in an[0]["label"].lower(), an[0]
    from ai_parsers.segmentasi_anatomi.koreksi import midline_x
    _, _lm = midline_x(st)
    assert _lm is True
    import copy as _copy
    f_nolm = _copy.deepcopy(f)
    P.align_text_laterality(f_nolm, _copy.deepcopy(an), landmark=False)
    assert "left" in f_nolm["diagnosis"].lower() and f_nolm["catatan_lateralitas"], f_nolm      # tanpa landmark: teks tidak dibalik otomatis
    P.align_text_laterality(f, an, landmark=True)
    assert "right" in f["diagnosis"].lower() and "left" not in f["summary"].lower(), f
    assert an[0]["lokasi_anatomi"][:2] == ["right_lung", "middle_zone_right"] and an[0]["lokasi_label"] == "Right middle zone", an[0]
    # 4) lesi benar tidak diubah, tetapi tertaut ke anatomi
    g = P.normalize_result(_pa_model_output(False))
    st, _ = P.reconcile_structures(g["structures"])
    a2 = g["anomalies"]
    P.refine_anomaly_geometry(a2, st)
    assert not a2[0].get("koreksi_lateralitas") and a2[0].get("lateralitas_cocok") and a2[0]["label"] == "Consolidation in the right middle zone", a2[0]
    # 5) zona pada teks tidak sesuai letak -> teks disesuaikan
    a3 = [{"label": "Consolidation in the right upper zone", "description": "", "box": {"xmin": .15, "ymin": .62, "xmax": .35, "ymax": .76}}]
    P.refine_anomaly_geometry(a3, st)
    assert "lower" in a3[0]["label"] and a3[0]["koreksi_zona"], a3[0]
    # 6) lapang pandang: struktur di area hitam dibuang, lesi di area hitam kehilangan lokasinya
    fov = (.3, 0.0, .7, 1.0)
    out, notes = P.reconcile_structures([{"id": "right_lung", "box": {"xmin": .05, "ymin": .2, "xmax": .2, "ymax": .8}},
                                        {"id": "left_lung", "box": {"xmin": .5, "ymin": .2, "xmax": .68, "ymax": .8}}], fov)
    assert [s["taxon"] for s in out if not s.get("derived")] == ["left_lung"] or "right_lung" not in [s["taxon"] for s in out], notes
    # 7) lesi tanpa kontur paru DAN tanpa landmark (mode lesi saja): teks TIDAK dibalik, hanya ditandai tidak pasti
    a4 = [{"label": "Left pleural effusion", "description": "", "box": {"xmin": .15, "ymin": .7, "xmax": .4, "ymax": .9}}]
    P.refine_anomaly_geometry(a4, [])
    assert a4[0]["label"] == "Left pleural effusion" and a4[0]["lateralitas_tidak_pasti"] and a4[0]["geometry_warning"], a4[0]
    assert not a4[0].get("koreksi_lateralitas"), a4[0]
    # 7b) kotak yang sama, tetapi ada landmark garis tengah (trakea + vertebra): sisi teks dikoreksi
    lm = [{"id": "trachea", "box": {"xmin": .47, "ymin": .05, "xmax": .53, "ymax": .3}},
          {"id": "thoracic_vertebrae_T1_T12", "box": {"xmin": .47, "ymin": .3, "xmax": .53, "ymax": .8}}]
    a4b = [{"label": "Left pleural effusion", "description": "", "box": {"xmin": .15, "ymin": .7, "xmax": .4, "ymax": .9}}]
    P.refine_anomaly_geometry(a4b, P.reconcile_structures(P.normalize_structures(lm))[0])
    assert "right" in a4b[0]["label"].lower() and a4b[0]["koreksi_lateralitas"], a4b[0]
    a5 = [{"label": "Cardiomegaly", "description": "", "box": {"xmin": .3, "ymin": .5, "xmax": .7, "ymax": .88}}]
    P.refine_anomaly_geometry(a5, [])
    assert a5[0]["label"] == "Cardiomegaly" and a5[0]["lokasi_anatomi"] == ["cardiac_silhouette"], a5[0]
    # 8) prompt memuat taksonomi dan aturan lokasi lesi
    sp = P.build_dynamic_system_prompt("gemini", scan_meta={"Anatomical Area": "Thorax / Chest"}, img_wh=(1024, 1024), fov=(.2, .1, .8, .95))
    assert "right_upper_lobe" in sp and "gastric_air_bubble" in sp and "lokasi_anatomi" in sp and "FIELD OF VIEW" in sp
    assert P.swap_side_words("Paru KANAN dan kiri, Right") == "Paru KIRI dan kanan, Left"
    print("taksonomi OK")
    return 0

def test_taksonomi():
    assert run_taksonomi() == 0


def run_koreksi_lesi():
    """Koreksi letak lesi: pecah bilateral, buang lesi di bawah diafragma, kecilkan kotak raksasa, kontur di dalam kotak, diagnosis sinkron."""
    from ai_parsers.geo_utils import box_area
    lungs = [{"label": "Paru kanan", "polygon": [[.12, .15], [.3, .13], [.45, .25], [.46, .6], [.4, .82], [.2, .84], [.1, .6]]},
             {"label": "Paru kiri", "polygon": [[.56, .15], [.72, .13], [.88, .2], [.9, .6], [.85, .82], [.62, .84], [.55, .6]]}]
    st, _ = P.reconcile_structures(P.sanitize_structures(P.normalize_structures(lungs)))
    an = [
        {"label": "Bilateral diffuse opacity", "box": {"xmin": .05, "ymin": .1, "xmax": .95, "ymax": .85}, "severity_score": .7, "description": ""},
        {"label": "Ill-defined hazy opacity in the right lower zone", "box": {"xmin": .1, "ymin": .88, "xmax": .4, "ymax": .98}, "severity_score": .2, "description": ""},
        {"label": "Small left pleural effusion", "box": {"xmin": .6, "ymin": .9, "xmax": .9, "ymax": .99}, "severity_score": .4, "description": ""},
        {"label": "Focal consolidation in the right middle zone", "box": {"xmin": .1, "ymin": .2, "xmax": .46, "ymax": .8},
         "polygon": [[.1, .2], [.46, .2], [.46, .8], [.1, .8]], "severity_score": .6, "description": ""},
    ]
    an = P.sanitize_anomaly_geometry(an)
    P.refine_anomaly_geometry(an, st)
    kept = [a for a in an if not a.get("_drop")]
    dropped = [a for a in an if a.get("_drop")]
    assert len(dropped) == 2, [a["label"] for a in dropped]                      # di bawah diafragma dibuang
    sides = [a for a in kept if "Bilateral" in a["label"]]
    assert len(sides) == 2 and sides[0]["box"]["xmax"] <= .47 and sides[1]["box"]["xmin"] >= .55, sides      # satu kotak per paru
    foc = [a for a in kept if "Focal" in a["label"]][0]
    assert box_area(foc["box"]) < 0.16, foc["box"]                                 # kotak fokal diperkecil
    pb = P.geometry._box_from_poly(foc["polygon"])
    assert pb["xmin"] >= foc["box"]["xmin"] - 1e-3 and pb["xmax"] <= foc["box"]["xmax"] + 1e-3, (pb, foc["box"])   # kontur (heatmap) di dalam kotak
    res = {"diagnosis": "Right lobar pneumonia", "confidence": .8, "diagnosis_alternatif": [], "diagnosis_code": "CA40"}
    eff = [{"label": "Right pleural effusion", "description": "", "box": {"xmin": .1, "ymin": .7, "xmax": .4, "ymax": .8}, "severity_score": .4}]
    note = P.sync_diagnosis_with_findings(res, eff, ["Right middle zone consolidation"])
    assert note and res["diagnosis"] == "Right lobar pneumonia" and res["diagnosis_perlu_verifikasi"] and res["confidence"] <= 0.5, res   # diagnosis dipertahankan
    assert "Right pleural effusion" in res["diagnosis_alternatif"], res                                                                # temuan tervalidasi jadi alternatif
    ok = {"diagnosis": "Right lobar pneumonia", "confidence": .6, "diagnosis_alternatif": []}
    P.sync_diagnosis_with_findings(ok, [foc], [])
    assert ok["diagnosis"] == "Right lobar pneumonia", ok                          # didukung konsolidasi: tidak diubah
    kl, rm = P.strip_nonlesion_findings([{"label": "Hazy opacity, likely soft tissue overlay"}, {"label": "Consolidation"}])
    assert len(kl) == 1 and len(rm) == 1
    print("koreksi lesi OK")
    return 0

def test_koreksi_lesi():
    assert run_koreksi_lesi() == 0


if __name__ == "__main__":
    sys.exit(1 if (run() or run_thorax() or run_mode_dan_keparahan() or run_taksonomi() or run_koreksi_lesi()) else 0)
