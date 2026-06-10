$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BackendPath = Join-Path $ProjectRoot "backend"
$FrontendPath = Join-Path $ProjectRoot "frontend"
$DataPath = Join-Path $ProjectRoot "data"

New-Item -ItemType Directory -Force -Path $DataPath | Out-Null

function New-PrintBillingPassword {
    -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object {[char]$_})
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python nao encontrado. Instale Python 3.12 LTS de https://www.python.org/downloads/windows/ e marque 'Add python.exe to PATH'."
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js nao encontrado. Instale Node.js LTS de https://nodejs.org/."
}

$secret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 64 | ForEach-Object {[char]$_})
$adminPassword = New-PrintBillingPassword
$agentPassword = New-PrintBillingPassword
$backendEnv = @"
DATABASE_URL=sqlite:///$($DataPath.Replace('\','/'))/printbilling.db
SECRET_KEY=$secret
CORS_ORIGINS=["http://localhost:3000"]
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=$adminPassword
INITIAL_AGENT_USERNAME=agent
INITIAL_AGENT_PASSWORD=$agentPassword
DEFAULT_MONTHLY_QUOTA=500
AUTO_CREATE_USERS=true
AUTO_CREATE_PRINTERS=true
"@

Set-Content -LiteralPath (Join-Path $BackendPath ".env") -Value $backendEnv -Encoding UTF8
Set-Content -LiteralPath (Join-Path $FrontendPath ".env.local") -Value "NEXT_PUBLIC_API_URL=http://localhost:8000" -Encoding UTF8
Set-Content -LiteralPath (Join-Path $DataPath "initial-credentials.txt") -Value @"
Sistema de Bilhetagem - credenciais iniciais

Admin: admin
Senha admin: $adminPassword

Agent: agent
Senha agent: $agentPassword
"@ -Encoding UTF8

Set-Location $BackendPath
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt

Set-Location $FrontendPath
npm install
npm run build

Write-Host ""
Write-Host "Instalacao Lite concluida."
Write-Host "Credenciais iniciais salvas em: $(Join-Path $DataPath "initial-credentials.txt")"
Write-Host "Use .\deploy\lite-start.ps1 para iniciar o sistema."
