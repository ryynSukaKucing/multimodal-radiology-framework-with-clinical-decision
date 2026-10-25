"""Alur dua panggilan: (1) deteksi objek saja [kotak], (2) segmentasi lewat /api/scan/{id}/segment [kontur]. Router AI palsu, tanpa jaringan."""
import json

import httpx
import pytest

from test_scan_flow import _png, _msg, _rows, _reset, client, _RealAsync   # noqa: F401  (impor ini juga menyiapkan env + database uji)
import ai_parsers
from config import detect_max_tokens_for, segment_max_tokens_for, settings


def _box(x0, y0, x1, y1):
    return {"xmin": x0, "ymin": y0, "xmax": x1, "ymax": y1}


DETECT = {
    "diagnosis": "Right middle zone consolidation", "confidence": 0.6, "summary": "Consolidation in the right middle zone.",
    "anomalies": [{"label": "Consolidation in the right middle zone", "severity": "Moderate", "severity_score": 0.5, "description": "opacity",
                   "box": _box(.15, .40, .35, .55), "lokasi_anatomi": ["right_lung"],
                   "polygon": [[.2, .42], [.3, .42], [.3, .5], [.2, .5]]}],          # kontur nyasar pada panggilan 1: harus dibuang
    "structures": [{"id": "right_lung", "box": _box(.10, .15, .45, .75), "polygon": [[.1, .15], [.45, .15], [.45, .75], [.1, .75]]},
                   {"id": "left_lung", "box": _box(.55, .15, .90, .75)}],
}
SEGMENT = {
    "anomalies": [{"id": "lesion_1", "polygon": [[.17, .42], [.33, .42], [.34, .50], [.30, .54], [.18, .53]]}],
    "structures": [{"id": "right_lung", "polygon": [[.12, .17], [.42, .17], [.44, .40], [.43, .72], [.14, .72], [.11, .40]]},
                   {"id": "left_lung", "polygon": [[.58, .17], [.88, .17], [.89, .40], [.86, .72], [.57, .72], [.56, .40]]}],
}


@pytest.fixture
def two(monkeypatch):
    state = {"detect": _msg(json.dumps(DETECT)), "segment": _msg(json.dumps(SEGMENT)), "calls": [], "bodies": []}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        first = body["messages"][0]["content"]
        text = str(first[0].get("text", "")) if isinstance(first, list) else str(first)
        kind = "segment" if ai_parsers.SEGMENTATION_MARK in text else "detect"
        state["calls"].append(kind)
        state["bodies"].append(body)
        return httpx.Response(200, json=state[kind])

    class Fake(_RealAsync):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", Fake)
    monkeypatch.setattr(settings, "GROUNDING_PASS", False)
    return state


def _detect():
    return client.post("/api/scan", files={"file": ("x.png", _png(), "image/png")}, data={"model": "oc/test-model", "mode_pindai": "anatomi_lesi"})


def test_panggilan_1_hanya_deteksi_kontur_nyasar_dibuang_dan_token_minimal_8000(two):
    _reset()
    r = _detect()
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert two["calls"] == ["detect"]                                     # tepat satu panggilan model pada tahap deteksi
    assert two["bodies"][0]["max_tokens"] >= 8000
    assert d["segmented"] is False and d["stage"] == "detect"
    assert d["anomalies"] and d["anomalies"][0].get("box") and not d["anomalies"][0].get("polygon")
    assert d["structures"] and all(not s.get("polygon") and not s.get("polyline") for s in d["structures"])
    assert r.json()["history"]["segmented"] == 0
    prompt = two["bodies"][0]["messages"][0]["content"][0]["text"]
    assert "OBJECT DETECTION ONLY" in prompt and "STAGE 3" not in prompt and "STAGE 4" not in prompt


def test_panggilan_2_segmentasi_menambah_kontur_tanpa_mengubah_kotak(two):
    _reset()
    first = _detect().json()
    hid = first["history"]["id"]
    box_before = first["data"]["anomalies"][0]["box"]
    r = client.post(f"/api/scan/{hid}/segment", data={"model": "oc/test-model"})
    assert r.status_code == 200, r.text
    assert two["calls"] == ["detect", "segment"]                         # total tepat dua panggilan
    assert two["bodies"][1]["max_tokens"] >= 8000
    seg_prompt = two["bodies"][1]["messages"][0]["content"][0]["text"]
    assert "lesion_1" in seg_prompt and "right_lung" in seg_prompt          # kotak final dari panggilan 1 dikirim ke panggilan 2
    d = r.json()["data"]
    assert d["segmented"] is True and r.json()["history"]["segmented"] == 1
    an = d["anomalies"][0]
    assert an["polygon"] and len(an["polygon"]) >= 3
    assert an["box"] == box_before
    lungs = {s["taxon"]: s for s in d["structures"]}
    assert lungs["right_lung"].get("polygon") and lungs["left_lung"].get("polygon")
    assert any(s.get("derived") for s in d["structures"])                  # zona paru diturunkan dari kontur paru
    row = _rows("success")[0]
    assert row.segmented == 1 and json.loads(row.anomalies_json)[0]["polygon"]


def test_segmentasi_gagal_tidak_merusak_hasil_deteksi(two):
    _reset()
    hid = _detect().json()["history"]["id"]
    two["segment"] = _msg("maaf, tidak bisa")
    r = client.post(f"/api/scan/{hid}/segment", data={"model": "oc/test-model"})
    assert r.status_code == 502
    row = _rows("success")[0]
    assert row.segmented == 0 and not json.loads(row.anomalies_json)[0].get("polygon") and json.loads(row.anomalies_json)[0].get("box")


def test_segmentasi_tanpa_objek_terdeteksi_ditolak(two):
    _reset()
    two["detect"] = _msg(json.dumps({"diagnosis": "Normal", "confidence": 0.7, "summary": "ok", "anomalies": [],
                                     "structures": [{"id": "trachea", "box": _box(.47, .1, .53, .4)}]}))
    # trachea berbentuk polygon bertier 1 sehingga tetap bisa disegmentasi; pakai riwayat tanpa kotak sama sekali:
    hid = _detect().json()["history"]["id"]
    import models
    from database import SessionLocal
    db = SessionLocal(); it = db.query(models.ScanHistory).get(hid); it.anomalies_json = "[]"; it.structures_json = "[]"; db.commit(); db.close()
    r = client.post(f"/api/scan/{hid}/segment", data={"model": "oc/test-model"})
    assert r.status_code == 400 and two["calls"] == ["detect"]


def test_batas_token_tidak_pernah_di_bawah_8000(monkeypatch):
    monkeypatch.setattr(settings, "DETECT_MAX_TOKENS", 500)
    monkeypatch.setattr(settings, "SEGMENT_MAX_TOKENS", 500)
    assert detect_max_tokens_for("kr/claude-sonnet-4.5") == 8000 and segment_max_tokens_for("kr/claude-sonnet-4.5") == 8000
    assert detect_max_tokens_for("x/deepseek-r1") >= 8000 and segment_max_tokens_for("x/deepseek-r1") >= 8000


def test_prompt_penuh_masih_memuat_segmentasi_tetapi_prompt_deteksi_tidak():
    full = ai_parsers.build_dynamic_system_prompt("claude", mode_pindai="anatomi_lesi")
    det = ai_parsers.build_dynamic_system_prompt("claude", mode_pindai="anatomi_lesi", stage="detect")
    assert "ANATOMICAL SEGMENTATION (stage 3)" in full and "LESION SEGMENTATION (stage 4)" in full
    assert "ANATOMICAL SEGMENTATION (stage 3)" not in det and "LESION SEGMENTATION (stage 4)" not in det
    assert len(det) < len(full)
