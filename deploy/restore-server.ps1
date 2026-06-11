param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$ProjectPath = "C:\Bilhetagem",
    [string]$DatabaseService = "postgres",
    [string]$DatabaseName = "",
    [string]$DatabaseUser = "",
    [switch]$RestoreAgentReleases,
    [switch]$Force
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

$resolvedProject = Resolve-Path -LiteralPath $ProjectPath -ErrorAction Stop
$resolvedBackup = Resolve-Path -LiteralPath $BackupPath -ErrorAction Stop
$BackupPath = $resolvedBackup.Path
$ProjectPath = $resolvedProject.Path

$dumpPath = Join-Path $BackupPath "postgres.sql"
if (-not (Test-Path $dumpPath)) {
    throw "Arquivo postgres.sql nao encontrado em: $BackupPath"
}

if (-not $Force) {
    throw "Restauracao bloqueada. Execute novamente com -Force depois de confirmar que este e o backup correto: $BackupPath"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker nao encontrado."
}

$DatabaseName = if ($DatabaseName) { $DatabaseName } else { Get-EnvValue -Name "POSTGRES_DB" -Default "printbilling" }
$DatabaseUser = if ($DatabaseUser) { $DatabaseUser } else { Get-EnvValue -Name "POSTGRES_USER" -Default "printbilling" }

Push-Location $ProjectPath
$servicesStopped = $false
try {
    Write-Host "Gerando backup de seguranca antes da restauracao..."
    & (Join-Path $ProjectPath "deploy\backup-server.ps1") -ProjectPath $ProjectPath -DatabaseService $DatabaseService -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser -SkipAgentReleases

    Write-Host "Parando backend/frontend durante a restauracao..."
    docker compose stop backend frontend | Out-Host
    $servicesStopped = $true

    Write-Host "Restaurando banco a partir de $dumpPath"
    Get-Content -LiteralPath $dumpPath -Raw | docker compose exec -T $DatabaseService psql -U $DatabaseUser -d $DatabaseName -v ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) {
        throw "psql falhou com codigo $LASTEXITCODE"
    }

    if ($RestoreAgentReleases) {
        $releasesZip = Join-Path $BackupPath "agent-releases.zip"
        if (-not (Test-Path $releasesZip)) {
            throw "agent-releases.zip nao encontrado no backup."
        }
        $releasesPath = Join-Path $ProjectPath "agent\releases"
        $resolvedProjectPath = (Resolve-Path -LiteralPath $ProjectPath).Path
        $targetParent = Split-Path -Parent $releasesPath
        $resolvedTargetParent = (Resolve-Path -LiteralPath $targetParent).Path
        if (-not $resolvedTargetParent.StartsWith($resolvedProjectPath, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Destino de releases fora do projeto: $releasesPath"
        }
        if (Test-Path $releasesPath) {
            Remove-Item -LiteralPath $releasesPath -Recurse -Force
        }
        Expand-Archive -LiteralPath $releasesZip -DestinationPath $targetParent -Force
    }

    Write-Host ""
    Write-Host "Restauracao concluida."
} finally {
    if ($servicesStopped) {
        Write-Host "Reiniciando backend/frontend..."
        docker compose up -d backend frontend | Out-Host
    }
    Pop-Location
}
