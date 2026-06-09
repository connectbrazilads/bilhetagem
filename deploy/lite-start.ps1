$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BackendPath = Join-Path $ProjectRoot "backend"
$FrontendPath = Join-Path $ProjectRoot "frontend"

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$BackendPath'; .\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
)

Start-Sleep -Seconds 3

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$FrontendPath'; npm start"
)

Write-Host "Backend:  http://localhost:8000"
Write-Host "Frontend: http://localhost:3000"
Write-Host "API Docs: http://localhost:8000/docs"
