"""Uji alur /api/scan end-to-end dengan router AI palsu (tanpa jaringan). Kriteria P0-1: jawaban meta/perintah shell -> HTTP 502, bukan riwayat sukses."""
import io, json, os, sys, tempfile
_TMP = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"       # harus diset SEBELUM config/database diimpor
os.environ["UPLOAD_DIR"] = f"{_TMP}/uploads"
os.environ["NINEROUTER_URL"] = "http://router.test/v1/chat/completions"
os.environ["NINEROUTER_API_KEY"] = "test-key"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

import models
from database import Base, engine, SessionLocal
from routers import scan as scan_router
from security import get_current_user

app = FastAPI()
app.include_router(scan_router.router)
app.dependency_overrides[get_current_user] = lambda: models.User(id=1, username="t", hashed_password="x", full_name="T", role="admin")
Base.metadata.create_all(bind=engine)
client = TestClient(app)

_RealAsync = httpx.AsyncClient


def _png() -> bytes:
    im = Image.new("L", (400, 300), 40)
    ImageDraw.Draw(im).ellipse([120, 80, 280, 220], fill=200)
    buf = io.BytesIO(); im.save(buf, "PNG")
    return buf.getvalue()


def _msg(content="", **extra):
    return {"choices": [{"message": dict({"content": content}, **extra), "finish_reason": "stop"}]}


@pytest.fixture
def router(monkeypatch):
    """Pasang router palsu: scan(msgs) menjawab panggilan analisis, repair(msgs) menjawab permintaan perapian JSON."""
    state = {"scan": _msg(""), "repair": _msg(""), "ground": _msg("{}"), "calls": []}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        first = body["messages"][0]["content"]
        is_repair = isinstance(first, str)
        is_ground = (not is_repair) and "GROUNDING PASS" in str(first[0].get("text", ""))
        kind = "repair" if is_repair else "ground" if is_ground else "scan"
        state["calls"].append(kind)
        assert request.headers.get("authorization") == "Bearer test-key"
        return httpx.Response(200, json=state[kind])

    class Fake(_RealAsync):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", Fake)
    return state


def _post(model="oc/test-model"):
    return client.post("/api/scan", files={"file": ("x.png", _png(), "image/png")},
                       data={"model": model, "mode_pindai": "anatomi_lesi"})


def _rows(status=None):
    db = SessionLocal()
    try:
        q = db.query(models.ScanHistory)
        if status:
            q = q.filter(models.ScanHistory.status == status)
        return q.all()
    finally:
        db.close()


def _reset():
    db = SessionLocal()
    db.query(models.ScanHistory).delete(); db.commit(); db.close()


def test_perintah_shell_lalu_repair_meta_menghasilkan_502_bukan_riwayat_sukses(router):
    _reset()
    router["scan"] = _msg("I will run: cat x | jq '{...}'")
    router["repair"] = _msg(json.dumps({"diagnosis": "No radiological findings present; input contains a shell command",
                                        "confidence": 0.9, "summary": "No findings.", "anomalies": [], "structures": []}))
    r = _post()
    assert r.status_code == 502, r.text
    assert "valid" in r.json()["detail"].lower()
    assert not _rows("success") and len(_rows("error")) == 1
    assert router["calls"] == ["scan", "repair"]


def test_model_repair_menjawab_not_radiology_text_menghasilkan_502(router):
    _reset()
    router["scan"] = _msg("sorry, here is a shell script: rm -rf {x}")
    router["repair"] = _msg('{"error":"not_radiology_text"}')
    r = _post()
    assert r.status_code == 502 and not _rows("success")


def test_hasil_repair_tanpa_temuan_dan_struktur_ditolak_walau_tanpa_teks_meta(router):
    _reset()
    router["scan"] = _msg("cuma prosa tanpa json")
    router["repair"] = _msg(json.dumps({"diagnosis": "Normal chest", "confidence": 0.8, "summary": "ok", "anomalies": [], "structures": []}))
    r = _post()
    assert r.status_code == 502 and not _rows("success")


def test_reasoning_perintah_shell_tanpa_content_ditolak(router):
    _reset()
    router["scan"] = _msg("", reasoning_content="I will run: cat x | jq '{...}'")
    r = _post()
    assert r.status_code == 502 and not _rows("success")
    assert router["calls"] == ["scan"]            # teks kosong: tidak ada gunanya meminta repair


def test_jawaban_prosa_valid_ditampilkan_dengan_needs_review(router):
    _reset()
    router["scan"] = _msg("Diagnosis: possible right lower zone pneumonia. Opacity seen at the base.")
    router["repair"] = _msg("I could not produce JSON")
    r = _post()
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["needs_review"] is True and d["parse_mode"] == "text_fallback" and d["anomalies"] == []


def test_json_sah_tersimpan_sukses_diagnosis_tidak_diganti_dan_lateralitas_tidak_dibalik(router):
    _reset()
    router["scan"] = _msg(json.dumps({
        "diagnosis": "Heart failure", "confidence": 0.8, "summary": "Pleural effusion in the left lower zone.",
        "anomalies": [{"label": "Pleural effusion in the left lower zone", "severity": "Moderate", "description": "basal opacity",
                       "box": {"xmin": 0.15, "ymin": 0.7, "xmax": 0.35, "ymax": 0.85}}]}))
    r = _post()
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["diagnosis"] == "Heart failure"                                  # tidak ditimpa label lesi
    assert d["diagnosis_perlu_verifikasi"] is True and d["confidence"] <= 0.5
    an = d["anomalies"][0]
    assert "left" in an["label"].lower() and an["lateralitas_tidak_pasti"] is True    # kotak di sisi kiri citra, tanpa bukti kuat: teks tetap
    assert "pleural effusion" in " ".join(d["diagnosis_alternatif"]).lower()
    assert len(_rows("success")) == 1 and router["calls"] == ["scan"]      # bawaan: hanya panggilan deteksi (grounding mati)
