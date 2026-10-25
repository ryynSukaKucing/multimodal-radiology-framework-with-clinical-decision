@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM setup.bat - Setup & jalankan backend Radiologi AI (Windows)
REM
REM CATATAN TEKNIS: skrip ini sengaja ditulis TANPA blok if(...)else(...)
REM bergaya banyak baris, karena tanda kurung "(" ")" pada path
REM (mis. folder "Downloads\radiology_v2 (4)\backend") membuat parser
REM cmd.exe salah membaca batas blok. Semua percabangan pakai GOTO.
REM
REM Pemakaian:
REM   setup.bat          -> setup saja (buat/pakai venv, install jika perlu)
REM   setup.bat run       -> setup lalu langsung menjalankan server
REM ============================================================

set "SCRIPT_DIR=%~dp0"
if "%VENV_DIR%"=="" set "VENV_DIR=%USERPROFILE%\.radiology-venv"
set "REQ_FILE=%SCRIPT_DIR%requirements.txt"
set "HASH_FILE=%VENV_DIR%\.requirements.hash"

echo == Radiologi AI - Setup Backend (Windows) ==
echo Lokasi proyek : %SCRIPT_DIR%
echo Lokasi venv   : %VENV_DIR%
echo.

if exist "%VENV_DIR%" goto venv_exists
echo [1/3] Venv belum ada -^> membuat baru...
python -m venv "%VENV_DIR%"
goto after_venv

:venv_exists
echo [1/3] Venv sudah ada -^> dipakai ulang.

:after_venv
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Gagal mengaktifkan venv. Pastikan Python 3.10+ sudah terpasang dan tercatat di PATH.
    exit /b 1
)

if exist "%REQ_FILE%" goto req_exists
echo ERROR: requirements.txt tidak ditemukan.
echo Dicari di: %REQ_FILE%
exit /b 1

:req_exists
set "NEW_HASH="
for /f "skip=1 tokens=* delims=" %%H in ('certutil -hashfile "%REQ_FILE%" SHA256 ^| findstr /v "CertUtil"') do (
    if not defined NEW_HASH set "NEW_HASH=%%H"
)
set "NEW_HASH=%NEW_HASH: =%"

set "OLD_HASH="
if exist "%HASH_FILE%" set /p OLD_HASH=<"%HASH_FILE%"

if "%NEW_HASH%"=="%OLD_HASH%" goto skip_install

echo [2/3] requirements.txt baru/berubah sejak terakhir kali -^> menginstall dependencies...
pip install --upgrade pip -q
pip install -r "%REQ_FILE%"
if errorlevel 1 (
    echo ERROR: pip install gagal. Cek pesan error di atas ^(biasanya masalah koneksi internet^).
    exit /b 1
)
if not exist "%VENV_DIR%" mkdir "%VENV_DIR%"
> "%HASH_FILE%" echo %NEW_HASH%
echo       Selesai. Hash requirements.txt disimpan untuk cek berikutnya.
goto after_install

:skip_install
echo [2/3] requirements.txt tidak berubah -^> lewati instalasi ^(hemat waktu ^& kuota^).

:after_install
echo [3/3] Siap digunakan.
echo.

if not "%~1"=="run" goto show_manual

set "ENV_FILE=%SCRIPT_DIR%.env"
set "ENV_EXAMPLE=%SCRIPT_DIR%.env.example"
if exist "%ENV_FILE%" goto has_env
if not exist "%ENV_EXAMPLE%" goto no_env_example
copy "%ENV_EXAMPLE%" "%ENV_FILE%" >nul
echo File .env belum ada -^> disalin otomatis dari .env.example.
echo    -^> Sebaiknya sunting SECRET_KEY di .env sebelum dipakai serius.
echo.
:no_env_example
:has_env

cd /d "%SCRIPT_DIR%"
echo Menjalankan server di http://localhost:8000 ...
uvicorn main:app --reload --host 0.0.0.0 --port 8000
goto :eof

:show_manual
echo Setup selesai. Untuk menjalankan server:
echo   call "%VENV_DIR%\Scripts\activate.bat"
echo   cd /d "%SCRIPT_DIR%"
echo   uvicorn main:app --reload
echo.
echo Atau jalankan langsung sekaligus: setup.bat run

:eof
endlocal
