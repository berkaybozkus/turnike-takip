@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Ilk calistirma: paketler kuruluyor...
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt
)
echo Panel: http://127.0.0.1:8000
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
