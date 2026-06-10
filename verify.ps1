param(
    [switch]$SkipBackend,
    [switch]$SkipAgent,
    [switch]$SkipFrontend,
    [switch]$VerifyAgentRelease,
    [switch]$RequireAgentSignature,
    [switch]$RequireAgentMsi
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Script
    )

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Script
    Write-Host "OK: $Name" -ForegroundColor Green
}

function Get-PythonPath {
    param([string]$ProjectDir)

    $venvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    return "python"
}

function Test-PythonHasPytest {
    param([string]$PythonPath)

    & $PythonPath -c "import pytest" 2>$null
    return $LASTEXITCODE -eq 0
}

function Get-PytestPythonPath {
    param(
        [string]$ProjectDir,
        [string[]]$FallbackProjectDirs = @()
    )

    $candidates = New-Object System.Collections.Generic.List[string]
    $candidates.Add((Get-PythonPath $ProjectDir))
    foreach ($fallback in $FallbackProjectDirs) {
        $candidates.Add((Get-PythonPath $fallback))
    }
    $candidates.Add("python")

    foreach ($candidate in $candidates | Select-Object -Unique) {
        try {
            if (Test-PythonHasPytest $candidate) {
                return $candidate
            }
        } catch {
            continue
        }
    }

    throw "Nenhum interpretador Python com pytest encontrado. Instale pytest no .venv do projeto."
}

function Invoke-Npm {
    param(
        [string]$WorkingDirectory,
        [string[]]$Arguments
    )

    Push-Location $WorkingDirectory
    try {
        & npm @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "npm $($Arguments -join ' ') falhou com codigo $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

if (-not $SkipBackend) {
    Invoke-Step "Backend tests" {
        $backendDir = Join-Path $Root "backend"
        $python = Get-PytestPythonPath $backendDir
        & $python -m pytest (Join-Path $backendDir "app\tests")
        if ($LASTEXITCODE -ne 0) {
            throw "Testes do backend falharam com codigo $LASTEXITCODE"
        }
    }
}

if (-not $SkipAgent) {
    Invoke-Step "Agent tests" {
        $agentDir = Join-Path $Root "agent"
        $backendDir = Join-Path $Root "backend"
        $python = Get-PytestPythonPath $agentDir @($backendDir)
        & $python -m pytest (Join-Path $agentDir "tests")
        if ($LASTEXITCODE -ne 0) {
            throw "Testes do agent falharam com codigo $LASTEXITCODE"
        }
    }
}

if (-not $SkipFrontend) {
    Invoke-Step "Frontend lint" {
        Invoke-Npm -WorkingDirectory (Join-Path $Root "frontend") -Arguments @("run", "lint")
    }
    Invoke-Step "Frontend build" {
        Invoke-Npm -WorkingDirectory (Join-Path $Root "frontend") -Arguments @("run", "build")
    }
}

if ($VerifyAgentRelease) {
    Invoke-Step "Agent release artifacts" {
        $verifyScript = Join-Path $Root "agent\verify_release.ps1"
        $releaseArgs = @{}
        if ($RequireAgentSignature) { $releaseArgs.RequireSignature = $true }
        if ($RequireAgentMsi) { $releaseArgs.RequireMsi = $true }
        & $verifyScript @releaseArgs
    }
}

Write-Host ""
Write-Host "Verificacao concluida com sucesso." -ForegroundColor Green
