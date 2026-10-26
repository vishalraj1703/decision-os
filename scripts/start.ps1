# Start Decision OS: FastAPI on 127.0.0.1:8000 and Next.js on http://localhost:3000.
# First run installs dependencies and creates the env files with fresh secrets.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
    .\.venv\Scripts\python -m pip install -r requirements.txt
}
if (-not (Test-Path "web\node_modules")) { Push-Location web; npm ci; Pop-Location }
.\.venv\Scripts\python scripts\setup_env.py

$api = Start-Process -PassThru -WindowStyle Minimized -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "app.main:create_app", "--factory", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8000"
Write-Host "API started (pid $($api.Id)). Web app: http://localhost:3000  (login password: DEMO_PASSWORD in web\.env.local)"
Push-Location web
npm run dev
Pop-Location
Stop-Process -Id $api.Id -ErrorAction SilentlyContinue
