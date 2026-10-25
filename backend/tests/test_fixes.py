"""Uji kriteria 'selesai' dari instruksi perbaikan radiology_v26 (parser/koreksi). Jalankan: python -m pytest tests -q"""
import glob, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ai_parsers as P
from ai_parsers.diagnosa_medis.sinkron import describe_findings, sync_diagnosis_with_findings
from ai_parsers.segmentasi_anatomi import koreksi as AK

B = {"xmin": .1, "ymin": .1, "xmax": .2, "ymax": .2}
A = lambda label, sc=.5, **kw: dict({"label": label, "box": dict(B), "severity_score": sc, "description": ""}, **kw)


# ---------- P0-2 / P0-3
def test_reasoning_perintah_shell_tidak_jadi_jawaban():
    msg = {"content": "", "reasoning_content": "I will run: cat x | jq '{...}'"}
    assert P.extract_message_text(msg) == ""


def test_reasoning_berisi_hasil_tetap_diterima():
    msg = {"content": "", "reasoning_content": 'hasil: {"diagnosis": "A", "anomalies": []}'}
    assert '"diagnosis"' in P.extract_message_text(msg)


def test_repair_prompt_punya_jalur_gagal_dan_deteksi_penolakan():
    assert 'not_radiology_text' in P.REPAIR_PROMPT
    assert P.repair_refused('{"error":"not_radiology_text"}') and P.repair_refused('```json\n{"error": "not_radiology_text"}\n```')
    assert not P.repair_refused('{"diagnosis": "x"}') and not P.repair_refused("")


# ---------- P1-4
def test_lesi_left_tanpa_kontur_dan_landmark_tetap_left_dan_tidak_pasti():
    a = [{"label": "Opacity in the left upper zone", "description": "", "box": {"xmin": .15, "ymin": .2, "xmax": .35, "ymax": .4}}]
    P.refine_anomaly_geometry(a, [])
    assert "left" in a[0]["label"].lower() and "right" not in a[0]["label"].lower()
    assert a[0]["lateralitas_tidak_pasti"] is True and a[0]["geometry_warning"]


def test_align_text_laterality_tidak_membalik_tanpa_bukti_kuat():
    res = {"diagnosis": "Left lobar pneumonia", "summary": "Opacity in the left upper zone.", "soap": {"assessment": "left lung"}}
    a = [{"label": "Opacity in the left upper zone", "description": "", "box": {"xmin": .15, "ymin": .2, "xmax": .35, "ymax": .4}}]
    P.refine_anomaly_geometry(a, [])
    note = P.align_text_laterality(res, a, landmark=False)
    assert note and res["diagnosis"] == "Left lobar pneumonia" and res["summary"].startswith("Opacity in the left")
    assert res["soap"]["assessment"] == "left lung" and res["catatan_lateralitas"]


def test_sumber_perkiraan_bukan_kontur_paru():
    lungs = AK  # noqa: F841 (impor memastikan modul termuat)
    from ai_parsers.segmentasi_lesi.koreksi import _locate, _prior_lungs
    side, lid, t, src = _locate((0.2, 0.5), _prior_lungs(None), 0.5, 1.0, False)
    assert side == "R" and src == "perkiraan" and t is None


# ---------- P1-5
def test_dua_lesi_kongesti_kiri_kanan_tidak_berulang():
    d = describe_findings([A("Perihilar congestion in the right lung"), A("Perihilar congestion in the left lung")])
    assert d == "Bilateral perihilar congestion", d
    assert d.lower().count("congestion") == 1


def test_diagnosis_dipertahankan_bukan_diganti_label_lesi():
    r = {"diagnosis": "Heart failure", "confidence": .8, "diagnosis_code": "I50", "diagnosis_alternatif": ["Pneumonia"]}
    note = sync_diagnosis_with_findings(r, [A("Right pleural effusion")])
    assert note and r["diagnosis"] == "Heart failure" and r["diagnosis_code"] == "I50"
    assert r["confidence"] <= .5 and r["diagnosis_perlu_verifikasi"] is True
    assert r["diagnosis_alternatif"][0] == "Right pleural effusion" and "Pneumonia" in r["diagnosis_alternatif"]


def test_sinkron_idempoten_dan_diagnosis_didukung_tidak_disentuh():
    r = {"diagnosis": "Right pleural effusion", "confidence": .7}
    assert sync_diagnosis_with_findings(r, [A("Right pleural effusion")]) is None and r["confidence"] == .7 and "diagnosis_perlu_verifikasi" not in r


# ---------- P1-6
def test_margin_dan_struktur_tier1_diberi_peringatan_bukan_dibuang():
    assert AK.PRIOR_MARGIN == 0.20
    # paru kanan jauh di luar jendela posisi taksonomi (tier 1): tetap ada + peringatan; struktur tier 3 yang meleset dibuang & tercatat
    st = [{"id": "right_lung", "box": {"xmin": .55, "ymin": .02, "xmax": .62, "ymax": .12}},
          {"id": "left_lung", "box": {"xmin": .55, "ymin": .2, "xmax": .9, "ymax": .8}}]
    out, notes, dropped = AK.reconcile_structures_ex(st)
    ids = [s["taxon"] for s in out if not s.get("derived")]
    assert "right_lung" in ids, (ids, notes)
    rl = [s for s in out if s["taxon"] == "right_lung"][0]
    assert rl.get("geometry_warning"), rl


def test_struktur_dibuang_tercatat_di_log_dan_daftar():
    st = [{"id": "right_lung", "box": {"xmin": .1, "ymin": .2, "xmax": .45, "ymax": .8}},
          {"id": "left_lung", "box": {"xmin": .55, "ymin": .2, "xmax": .9, "ymax": .8}},
          {"id": "left_clavicle", "box": {"xmin": .05, "ymin": .9, "xmax": .1, "ymax": .98}},     # jauh dari posisi lazim klavikula
          {"label": "Kateter vena sentral", "box": {"xmin": .5, "ymin": .1, "xmax": .52, "ymax": .5}}]
    out, notes, dropped = AK.reconcile_structures_ex(st)
    assert dropped, notes
    for d in dropped:
        assert d["label"] and d["alasan"]
        assert any(d["label"] in n for n in notes), (d, notes)       # setiap yang dibuang muncul juga di log
    assert P.reconcile_structures(st)[0] == out or len(P.reconcile_structures(st)[0]) == len(out)   # pembungkus kompatibel


# ---------- P2-8
def test_contoh_jsonl_tanpa_angka_koordinat():
    root = os.path.join(os.path.dirname(__file__), "..", "ai_parsers")
    files = glob.glob(os.path.join(root, "*", "contoh.jsonl"))
    assert len(files) == 5

    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("box", "polygon", "polyline", "centerline", "keypoints", "pointer"):
                    nums = []
                    def collect(x):
                        if isinstance(x, bool): return
                        if isinstance(x, (int, float)): nums.append(x)
                        elif isinstance(x, dict): [collect(i) for i in x.values()]
                        elif isinstance(x, list): [collect(i) for i in x]
                    collect(v)
                    assert not nums, (path + "/" + k, nums)
                walk(v, path + "/" + k)
        elif isinstance(o, list):
            for i in o: walk(i, path)

    for f in files:
        for ln in open(f, encoding="utf-8"):
            if ln.strip():
                r = json.loads(ln)
                walk(r["jawaban"], os.path.basename(os.path.dirname(f)))
                assert "xmin" not in r["prompt"].lower().replace("xmin,ymin", ""), r["prompt"]


def test_pembungkus_contoh_berbahasa_inggris_dan_prompt_tak_memuat_angka_contoh():
    sp = P.build_dynamic_system_prompt("gemini", scan_meta={"Anatomical Area": "Thorax / Chest"}, img_wh=(1024, 1024))
    assert "Masukan" not in sp and "Keluaran" not in sp and "Input:" in sp and "Output:" in sp
    assert '"xmin": 0.08' not in sp and '"xmin": 0.16' not in sp


def test_max_tokens_lebih_besar_untuk_model_berpikir():
    from config import max_tokens_for
    assert max_tokens_for("kr/claude-sonnet-4.5") == 8000
    assert max_tokens_for("oc/deepseek-v4.1-flash-free") > 8000 and max_tokens_for("oc/mimo-v2.6-flash-free") > 8000
