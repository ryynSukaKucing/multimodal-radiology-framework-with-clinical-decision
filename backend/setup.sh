#!/usr/bin/env bash
set -e

# ============================================================
# setup.sh - Setup & jalankan backend Radiologi AI (Linux/Mac)
#
# - Venv disimpan di LUAR folder proyek ($HOME/.radiology-venv secara default),
#   supaya bisa dipakai ulang lintas versi (v1, v2, v3, dst) tanpa install ulang.
# - Dependencies HANYA diinstall ulang kalau isi requirements.txt berubah
#   (dideteksi via hash SHA256), jadi update kode biasa tidak memicu install ulang.
#
# Pemakaian:
#   ./setup.sh          -> setup saja (buat/pakai venv, install jika perlu)
#   ./setup.sh run       -> setup lalu langsung menjalankan server
#
# Override lokasi venv (opsional), misal simpan di dalam proyek juga bisa:
#   VENV_DIR=./venv ./setup.sh run
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$HOME/.radiology-venv}"
REQ_FILE="$SCRIPT_DIR/requirements.txt"
HASH_FILE="$VENV_DIR/.requirements.hash"

echo "== Radiologi AI - Setup Backend =="
echo "Lokasi proyek : $SCRIPT_DIR"
echo "Lokasi venv   : $VENV_DIR  (dipakai bersama untuk semua versi proyek ini)"
echo

# 1. Buat venv kalau belum ada
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/3] Venv belum ada di $VENV_DIR -> membuat baru..."
    python3 -m venv "$VENV_DIR"
else
    echo "[1/3] Venv sudah ada -> dipakai ulang (tidak dibuat lagi)."
fi

# 2. Aktifkan venv
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# 3. Install/update dependencies HANYA jika requirements.txt berubah
if [ ! -f "$REQ_FILE" ]; then
    echo "ERROR: requirements.txt tidak ditemukan di $REQ_FILE"
    exit 1
fi

NEW_HASH=$(sha256sum "$REQ_FILE" | awk '{print $1}')
OLD_HASH=""
[ -f "$HASH_FILE" ] && OLD_HASH=$(cat "$HASH_FILE")

if [ "$NEW_HASH" != "$OLD_HASH" ]; then
    echo "[2/3] requirements.txt baru/berubah sejak terakhir kali -> menginstall dependencies..."
    pip install --upgrade pip -q
    pip install -r "$REQ_FILE"
    echo "$NEW_HASH" > "$HASH_FILE"
    echo "      Selesai. Hash requirements.txt disimpan untuk cek berikutnya."
else
    echo "[2/3] requirements.txt tidak berubah -> lewati instalasi (hemat waktu & kuota)."
fi

echo "[3/3] Siap digunakan."
echo

# 4. Jalankan server jika argumen "run" diberikan
if [ "${1:-}" == "run" ]; then
    if [ ! -f "$SCRIPT_DIR/.env" ] && [ -f "$SCRIPT_DIR/.env.example" ]; then
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
        echo "File .env belum ada -> disalin otomatis dari .env.example."
        echo "   -> Sebaiknya sunting SECRET_KEY di .env sebelum dipakai serius."
        echo
    fi
    cd "$SCRIPT_DIR"
    echo "Menjalankan server di http://localhost:8000 ..."
    exec uvicorn main:app --reload --host 0.0.0.0 --port 8000
else
    echo "Setup selesai. Untuk menjalankan server:"
    echo "  source \"$VENV_DIR/bin/activate\""
    echo "  cd \"$SCRIPT_DIR\" && uvicorn main:app --reload"
    echo
    echo "Atau jalankan langsung sekaligus: ./setup.sh run"
fi
