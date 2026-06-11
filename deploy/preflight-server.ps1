param(
    [string]$ProjectPath = "C:\Bilhetagem",
    [string]$FrontendUrl = "",
    [string]$ApiUrl = "",
    [int]$RecentBackupHours = 24,
    [switch]$SkipEndpointChecks,
    [switch]$RequireSignedAgent
)

$ErrorActionPreference = "Stop"
$script:Failures = 0
$script:Warnings = 0

function Add-Check {
    param(
        [ValidateSet("OK", "WARN", "FAIL")]
        [string]$Status,
        [string]$Message
    )

    $color = "Green"
    if ($Status -eq "WARN") {
        $script:Warnings += 1
        $color = "Yellow"
    }
    if ($Status -eq "FAIL") {
        $script:Failures += 1
        $color = "Red"
    }
    Write-Host "[$Status] $Message" -ForegroundColor $color
}

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

function Test-RequiredEnv {
    param([string[]]$Names)

    foreach ($name in $Names) {
        $value = Get-EnvValue -Name $name
        if ($value) {
            Add-Check "OK" ".env contem $name"
        } else {
            Add-Check "FAIL" ".env sem $name"
        }
    }
}

function Test-UnsafeSecret {
    param(
        [string]$Name,
        [string[]]$UnsafeValues
    )

    $value = Get-EnvValue -Name $Name
    if (-not $value) { return }
    if ($UnsafeValues -contains $value.Trim().ToLowerInvariant()) {
        Add-Check "FAIL" "$Name usa valor inseguro/padrao"
    } else {
        Add-Check "OK" "$Name nao usa valor padrao conhecido"
    }
}

function Test-AgentReleases {
    $manifestPath = Join-Path $ProjectPath "agent\releases\manifest.json"
    if (-not (Test-Path $manifestPath)) {
        Add-Check "FAIL" "agent\releases\manifest.json nao encontrado"
        return
    }

    try {
        $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    } catch {
        Add-Check "FAIL" "manifest.json do agent invalido"
        return
    }

    $release = @($manifest.versions)[0]
    if (-not $release) {
        Add-Check "FAIL" "manifest.json sem versoes publicadas"
        return
    }

    $releaseDir = Join-Path (Join-Path $ProjectPath "agent\releases") $release.version
    $files = @($release.files)
    $hasAgent = $files | Where-Object { $_.kind -eq "agent" } | Select-Object -First 1
    $hasInstaller = $files | Where-Object { $_.kind -eq "installer" } | Select-Object -First 1
    $hasMsi = $files | Where-Object { $_.kind -eq "msi" -or $_.filename -like "*.msi" } | Select-Object -First 1
    $checksums = Join-Path $releaseDir "SHA256SUMS.txt"

    Add-Check "OK" "release do agent encontrada: $($release.version)"
    foreach ($entry in @($hasAgent, $hasInstaller, $hasMsi)) {
        if (-not $entry) { continue }
        $path = Join-Path $releaseDir $entry.filename
        if (Test-Path $path) {
            Add-Check "OK" "artefato encontrado: $($entry.filename)"
        } else {
            Add-Check "FAIL" "artefato ausente: $($entry.filename)"
        }
        if ($RequireSignedAgent -and $entry.signature_status -ne "Valid") {
            Add-Check "FAIL" "$($entry.filename) sem assinatura valida"
        } elseif ($entry.signature_status -ne "Valid") {
            Add-Check "WARN" "$($entry.filename) sem assinatura digital valida"
        }
    }

    if (-not $hasAgent) { Add-Check "FAIL" "manifest sem binario agent" }
    if (-not $hasInstaller) { Add-Check "FAIL" "manifest sem instalador EXE" }
    if (-not $hasMsi) { Add-Check "WARN" "manifest sem MSI" }
    if (Test-Path $checksums) {
        Add-Check "OK" "SHA256SUMS.txt encontrado"
    } else {
        Add-Check "FAIL" "SHA256SUMS.txt ausente"
    }
}

function Test-RecentBackup {
    $backupRoot = Join-Path $ProjectPath "backups"
    if (-not (Test-Path $backupRoot)) {
        Add-Check "WARN" "pasta de backups ainda nao existe"
        return
    }

    $cutoff = (Get-Date).AddHours(-1 * $RecentBackupHours)
    $recent = Get-ChildItem -LiteralPath $backupRoot -Directory |
        Where-Object { $_.LastWriteTime -ge $cutoff -and (Test-Path (Join-Path $_.FullName "postgres.sql")) } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($recent) {
        Add-Check "OK" "backup recente encontrado: $($recent.Name)"
    } else {
        Add-Check "WARN" "nenhum backup com postgres.sql nas ultimas $RecentBackupHours horas"
    }
}

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Url,
        [string]$ExpectedText = ""
    )

    if (-not $Url) {
        Add-Check "WARN" "$Name sem URL configurada"
        return
    }

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
            if ($ExpectedText -and $response.Content -notlike "*$ExpectedText*") {
                Add-Check "WARN" "$Name respondeu, mas conteudo inesperado"
            } else {
                Add-Check "OK" "$Name respondeu em $Url"
            }
        } else {
            Add-Check "FAIL" "$Name respondeu HTTP $($response.StatusCode)"
        }
    } catch {
        Add-Check "FAIL" "$Name indisponivel em $Url ($($_.Exception.Message))"
    }
}

if (-not (Test-Path $ProjectPath)) {
    Add-Check "FAIL" "pasta do projeto nao encontrada: $ProjectPath"
    exit 1
}

$ProjectPath = (Resolve-Path -LiteralPath $ProjectPath).Path
Write-Host "Preflight PrintBilling: $ProjectPath"
Write-Host ""

if (Test-Path (Join-Path $ProjectPath ".env")) {
    Add-Check "OK" ".env encontrado"
} else {
    Add-Check "FAIL" ".env nao encontrado"
}

Test-RequiredEnv @("INITIAL_ADMIN_PASSWORD", "INITIAL_AGENT_PASSWORD", "SECRET_KEY", "PUBLIC_API_URL")
Test-UnsafeSecret -Name "SECRET_KEY" -UnsafeValues @("change-me-in-production", "change-this-secret-in-production-please")
Test-UnsafeSecret -Name "INITIAL_AGENT_PASSWORD" -UnsafeValues @("agent", "agent12345", "change-me-agent-password")
Test-UnsafeSecret -Name "INITIAL_ADMIN_PASSWORD" -UnsafeValues @("admin", "admin12345", "change-me-admin-password")

if (Get-Command docker -ErrorAction SilentlyContinue) {
    Add-Check "OK" "Docker encontrado"
} else {
    Add-Check "FAIL" "Docker nao encontrado"
}

Push-Location $ProjectPath
try {
    docker compose config *> $null
    if ($LASTEXITCODE -eq 0) {
        Add-Check "OK" "docker compose config valido"
        $runningServices = @(docker compose ps --services --filter "status=running" 2>$null)
        foreach ($service in @("postgres", "backend", "frontend")) {
            if ($runningServices -contains $service) {
                Add-Check "OK" "servico $service em execucao"
            } else {
                Add-Check "WARN" "servico $service nao esta em execucao"
            }
        }
    } else {
        Add-Check "FAIL" "docker compose config falhou"
    }
} catch {
    Add-Check "FAIL" "falha ao validar docker compose: $($_.Exception.Message)"
} finally {
    Pop-Location
}

Test-AgentReleases
Test-RecentBackup

if (-not $SkipEndpointChecks) {
    if (-not $ApiUrl) { $ApiUrl = Get-EnvValue -Name "PUBLIC_API_URL" -Default "http://localhost:8000" }
    if (-not $FrontendUrl) { $FrontendUrl = Get-EnvValue -Name "PUBLIC_FRONTEND_URL" -Default "http://localhost:3000" }
    Test-Endpoint -Name "API health" -Url "$($ApiUrl.TrimEnd('/'))/health" -ExpectedText "ok"
    Test-Endpoint -Name "Frontend" -Url $FrontendUrl -ExpectedText "PrintBilling"
}

Write-Host ""
Write-Host "Resumo: $script:Failures falha(s), $script:Warnings aviso(s)."
if ($script:Failures -gt 0) {
    exit 1
}
