$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (!(Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$port = if ($env:PORT) { $env:PORT } else { "8001" }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $port
