param(
    [string]$ProjectPath = "C:\Bilhetagem",
    [string]$BackupRoot = "",
    [string]$DatabaseService = "postgres",
    [string]$DatabaseName = "",
    [string]$DatabaseUser = "",
    [switch]$SkipAgentReleases
)

$ErrorActionPreference = "Stop"

function Get-EnvValue {
    param(
        [string]$Name,
        [string]$Default = ""
    )

    $value = [Environment]::GetEnvironmentVariable($Name)
    if ($value) { return $value }

    $envPath = Join-Path $ProjectPath ".env"
    if (-not (Test-Path $envPath)) { return $Default }

    $line = Get-Content -LiteralPath $envPath | Where-Object { $_ -match "^\s*$([regex]::Escape($Name))=" } | Select-Object -First 1
    if (-not $line) { return $Default }
    return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

if (-not (Test-Path $ProjectPath)) {
    throw "Pasta do projeto nao encontrada: $ProjectPath"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker nao encontrado."
}

if (-not $BackupRoot) {
    $BackupRoot = Join-Path $ProjectPath "backups"
}

$DatabaseName = if ($DatabaseName) { $DatabaseName } else { Get-EnvValue -Name "POSTGRES_DB" -Default "printbilling" }
$DatabaseUser = if ($DatabaseUser) { $DatabaseUser } else { Get-EnvValue -Name "POSTGRES_USER" -Default "printbilling" }
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $BackupRoot $timestamp
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

Push-Location $ProjectPath
try {
    docker compose ps --services --filter "status=running" | Out-Null

    $dumpPath = Join-Path $backupDir "postgres.sql"
    Write-Host "Gerando backup do banco em $dumpPath"
    docker compose exec -T $DatabaseService pg_dump -U $DatabaseUser -d $DatabaseName --clean --if-exists --no-owner --no-acl | Set-Content -LiteralPath $dumpPath -Encoding UTF8
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump falhou com codigo $LASTEXITCODE"
    }

    $metadata = [ordered]@{
        generated_at = (Get-Date).ToUniversalTime().ToString("o")
        project_path = $ProjectPath
        database_service = $DatabaseService
        database_name = $DatabaseName
        database_user = $DatabaseUser
        includes_agent_releases = -not $SkipAgentReleases
    }
    $metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $backupDir "metadata.json") -Encoding UTF8

    $envFile = Join-Path $ProjectPath ".env"
    if (Test-Path $envFile) {
        Copy-Item -LiteralPath $envFile -Destination (Join-Path $backupDir "env.backup") -Force
    }

    if (-not $SkipAgentReleases) {
        $releasesPath = Join-Path $ProjectPath "agent\releases"
        if (Test-Path $releasesPath) {
            Compress-Archive -LiteralPath $releasesPath -DestinationPath (Join-Path $backupDir "agent-releases.zip") -Force
        }
    }

    Write-Host ""
    Write-Host "Backup concluido: $backupDir"
} finally {
    Pop-Location
}
