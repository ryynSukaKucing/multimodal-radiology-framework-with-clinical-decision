"""Uji lintasan kedua: temuan yang disebut di teks harus punya kotak, dan CTR dihitung di kode (kasus nyata: kardiomegali tak terdeteksi)."""
import base64, io, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from test_scan_flow import router, _msg, _post, _reset, _rows, client   # noqa: F401  (fixture router dipakai ulang)

import numpy as np
from PIL import Image

import ai_parsers
from ai_parsers import grounding as g
from ai_parsers.diagnosa_medis.sinkron import sync_diagnosis_with_findings


def _box(x0, y0, x1, y1):
    return {"xmin": x0, "ymin": y0, "xmax": x1, "ymax": y1}


def _ground(heart=None, thorax=None, lungs=None, findings=None):
    return _msg(json.dumps({
        "heart": heart or {"level_y": 0.60, "right_border_x": 0.38, "left_border_x": 0.84, "top_y": 0.42, "bottom_y": 0.78},
        "thorax": thorax or {"right_inner_x": 0.14, "left_inner_x": 0.94},
        "lungs": lungs or {"right": _box(0.12, 0.10, 0.42, 0.62), "left": _box(0.62, 0.10, 0.94, 0.66)},
        "findings": findings or []}))


# ---------- find_ungrounded: empat kasus nyata dari layar ----------
def test_opasitas_basal_kiri_tanpa_kotak_terdeteksi_walau_ada_lesi_kanan():
    r = {"diagnosis": "Mild left basal opacity - suspected small left pleural effusion versus basal atelectasis"}
    an = [{"label": "Increased lower-zone interstitial markings in the right lung", "description": "", "box": _box(.17, .33, .44, .51)}]
    miss = g.find_ungrounded(r, an)
    assert len(miss) == 1 and miss[0]["side"] == "L"


def test_hilus_kiri_tanpa_lesi_terdeteksi():
    r = {"diagnosis": "Suspected left hilar nodular prominence, indeterminate; no acute cardiopulmonary abnormality"}
    miss = g.find_ungrounded(r, [])
    assert miss and miss[0]["side"] == "L"


def test_kasus_yang_sudah_lengkap_tidak_dianggap_kurang():
    r = {"diagnosis": "Suspected right middle and lower zone pneumonia with right pleural effusion"}
    an = [{"label": "Consolidation in the right middle and lower zone", "description": "", "box": _box(.2, .4, .5, .6)},
          {"label": "Right pleural effusion at the base", "description": "", "box": _box(.17, .6, .48, .72)}]
    assert g.find_ungrounded(r, an) == []


def test_temuan_dinegasikan_diabaikan():
    assert g.find_ungrounded({"diagnosis": "No pneumothorax, no pleural effusion; normal chest"}, []) == []


# ---------- CTR ----------
def test_ctr_dihitung_dari_landmark_dan_kategori():
    grounded = {"heart": {"level_y": .6, "right_border_x": .40, "left_border_x": .80, "top_y": .4, "bottom_y": .8},
                "thorax": {"right_inner_x": .14, "left_inner_x": .94}}
    info = g.compute_ctr(grounded)
    assert abs(info["ctr"] - 0.5) < 0.01 or info["ctr"] > 0.49
    grounded["heart"]["left_border_x"] = .85
    info = g.compute_ctr(grounded)
    assert info["ctr"] == round(0.45 / 0.80, 3) and info["kategori"] == "kardiomegali"


def test_landmark_tidak_masuk_akal_ditolak():
    bad = {"heart": {"level_y": .6, "right_border_x": .8, "left_border_x": .4, "top_y": .4, "bottom_y": .8},
           "thorax": {"right_inner_x": .14, "left_inner_x": .94}}
    assert g.compute_ctr(bad) is None
    assert g.compute_ctr({"heart": {}, "thorax": {}}) is None


def test_snap_menggeser_landmark_ke_tepi_piksel():
    a = np.full((200, 400), 0.15)                 # paru gelap
    a[:, 150:260] = 0.85                           # bayangan jantung 150..260 (x 0.375..0.65)
    a[:, :40] = 0.8; a[:, 360:] = 0.8              # dinding dada
    lm = {"level_y": .5, "right_border_x": .35, "left_border_x": .68, "right_inner_x": .12, "left_inner_x": .88}
    out, moved = g.snap_landmarks(a, lm)
    assert moved and abs(out["right_border_x"] - 0.375) < 0.02 and abs(out["left_border_x"] - 0.65) < 0.02


def test_apply_ctr_menambah_kardiomegali_dan_mengoreksi_ringkasan():
    res = {"diagnosis": "Mild left basal opacity", "summary": "Cardiac silhouette is not clearly enlarged.", "confidence": .45}
    an = []
    info = {"ctr": 0.58, "kategori": "kardiomegali", "sumber": "x", "lebar_jantung": .46, "lebar_toraks": .8, "level_y": .6,
            "box_jantung": _box(.4, .42, .86, .78)}
    g.apply_ctr(res, an, info)
    assert an and an[0]["label"].startswith("Cardiomegaly (CTR 0.58)") and an[0]["box"]
    assert "cardiomegaly" in res["diagnosis"].lower() and res["summary"].startswith("Cardiac size")
    assert res["diagnosis_perlu_verifikasi"] is True


# ---------- sinkron.py ----------
def test_diagnosis_bertemuan_tapi_anomalies_kosong_tidak_lolos_diam_diam():
    res = {"diagnosis": "Suspected left hilar nodular prominence, indeterminate; no acute cardiopulmonary abnormality", "confidence": .4}
    note = sync_diagnosis_with_findings(res, [], [])
    assert note and res["diagnosis_perlu_verifikasi"] is True


def test_konflik_sisi_diagnosis_vs_lesi():
    res = {"diagnosis": "Mild left basal opacity", "confidence": .6}
    an = [{"label": "Basal opacity in the right lung", "description": "opacity", "box": _box(.2, .5, .4, .7)}]
    note = sync_diagnosis_with_findings(res, an, [])
    assert note and "left" in note and res["confidence"] <= 0.5


# ---------- alur penuh /api/scan ----------
@pytest.fixture(autouse=True)
def _grounding_on(monkeypatch):
    """Grounding pass bawaannya mati (alur dua panggilan); tes di berkas ini memeriksa lintasan itu, jadi diaktifkan di sini."""
    from config import settings
    monkeypatch.setattr(settings, "GROUNDING_PASS", True)



def test_alur_penuh_kasus_kardiomegali_dan_opasitas_basal_kiri(router):
    _reset()
    router["scan"] = _msg(json.dumps({
        "diagnosis": "Mild left basal opacity - suspected small left pleural effusion versus basal atelectasis", "confidence": .45,
        "summary": "Cardiac silhouette is not clearly enlarged. Left costophrenic angle hazy.",
        "anomalies": [{"label": "Increased lower-zone interstitial markings in the right lung", "severity": "Low", "severity_score": .28,
                       "description": "markings", "box": _box(.17, .33, .44, .51)}]}))
    router["ground"] = _ground(findings=[{"label": "Left basal opacity with blunted costophrenic angle", "side": "left", "zone": "lower",
                                          "severity_score": 0.45, "description": "hazy left lower zone", "box": _box(.66, .60, .92, .76)}])
    r = _post()
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    labels = [a["label"] for a in d["anomalies"]]
    assert any("left basal opacity" in l.lower() for l in labels), labels
    assert any(l.startswith("Cardiomegaly (CTR") for l in labels), labels
    assert "cardiomegaly" in d["diagnosis"].lower()
    assert d["pengukuran_lokal"]["ctr"]["ctr"] > 0.5
    cardio = next(a for a in d["anomalies"] if a["label"].startswith("Cardiomegaly"))
    assert cardio["box"]["xmax"] - cardio["box"]["xmin"] > 0.3
    assert router["calls"] == ["scan", "ground"]
    assert len(_rows("success")) == 1


def test_alur_penuh_hilus_kiri_dari_anomalies_kosong(router):
    _reset()
    router["scan"] = _msg(json.dumps({
        "diagnosis": "Suspected left hilar nodular prominence, indeterminate; no acute cardiopulmonary abnormality", "confidence": .4,
        "summary": "A rounded density projects over the left hilum.", "anomalies": []}))
    router["ground"] = _ground(
        heart={"level_y": .62, "right_border_x": .42, "left_border_x": .66, "top_y": .45, "bottom_y": .78},
        thorax={"right_inner_x": .17, "left_inner_x": .90},
        findings=[{"label": "Left hilar nodular prominence", "side": "left", "zone": "hilar", "severity_score": 0.3,
                   "description": "rounded density", "box": _box(.58, .27, .70, .42)}])
    r = _post()
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert any("hilar" in a["label"].lower() and a.get("box") for a in d["anomalies"])
    assert not any(a["label"].startswith("Cardiomegaly") for a in d["anomalies"])      # CTR 0.33: normal, tidak dikarang
    assert d["pengukuran_lokal"]["ctr"]["kategori"] == "normal"


def test_lintasan_kedua_gagal_tidak_menggagalkan_pemindaian(router):
    _reset()
    router["scan"] = _msg(json.dumps({"diagnosis": "Right lower zone pneumonia", "confidence": .6, "summary": "Opacity in the right lower zone.",
                                      "anomalies": [{"label": "Consolidation in the right lower zone", "severity": "Moderate", "description": "x",
                                                     "box": _box(.17, .55, .42, .75)}]}))
    router["ground"] = _msg("bukan json sama sekali")
    r = _post()
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]["anomalies"]) == 1
