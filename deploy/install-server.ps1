param(
    [string]$ProjectPath = "C:\Bilhetagem",
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"

Set-Location $ProjectPath

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker nao encontrado. Instale Docker Desktop/Engine no servidor e execute novamente."
}

docker compose version | Out-Host

if ($Rebuild) {
    docker compose up --build -d
} else {
    docker compose up -d --build
}

docker compose ps

Write-Host ""
Write-Host "Bilhetagem iniciado."
Write-Host "Frontend: $env:PUBLIC_FRONTEND_URL"
Write-Host "API:      $env:PUBLIC_API_URL"
