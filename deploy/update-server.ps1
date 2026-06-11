param(
    [string]$ProjectPath = "C:\Bilhetagem",
    [string]$Branch = "main",
    [switch]$SkipGitPull,
    [switch]$SkipBackup,
    [switch]$SkipPreflight,
    [switch]$SkipEndpointChecks,
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ProjectPath)) {
    throw "Pasta do projeto nao encontrada: $ProjectPath"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker nao encontrado."
}

if (-not $SkipGitPull -and -not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git nao encontrado."
}

$ProjectPath = (Resolve-Path -LiteralPath $ProjectPath).Path
Push-Location $ProjectPath
try {
    Write-Host "Atualizacao PrintBilling: $ProjectPath"

    if (-not $SkipBackup) {
        Write-Host ""
        Write-Host "1/5 Backup antes da atualizacao"
        & (Join-Path $ProjectPath "deploy\backup-server.ps1") -ProjectPath $ProjectPath
    } else {
        Write-Host "1/5 Backup ignorado por parametro."
    }

    if (-not $SkipGitPull) {
        Write-Host ""
        Write-Host "2/5 Atualizando codigo pelo Git"
        $dirty = (git status --porcelain)
        if ($dirty -and -not $AllowDirty) {
            throw "Worktree com alteracoes locais. Use -AllowDirty apenas se souber que elas podem conviver com o pull."
        }
        git fetch origin $Branch
        if ($LASTEXITCODE -ne 0) { throw "git fetch falhou" }
        git checkout $Branch
        if ($LASTEXITCODE -ne 0) { throw "git checkout $Branch falhou" }
        git pull --ff-only origin $Branch
        if ($LASTEXITCODE -ne 0) { throw "git pull falhou" }
    } else {
        Write-Host "2/5 Git pull ignorado por parametro."
    }

    Write-Host ""
    Write-Host "3/5 Subindo containers"
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw "docker compose up falhou" }

    Write-Host ""
    Write-Host "4/5 Status dos servicos"
    docker compose ps

    if (-not $SkipPreflight) {
        Write-Host ""
        Write-Host "5/5 Preflight final"
        $preflightArgs = @{
            ProjectPath = $ProjectPath
        }
        if ($SkipEndpointChecks) {
            $preflightArgs.SkipEndpointChecks = $true
        }
        & (Join-Path $ProjectPath "deploy\preflight-server.ps1") @preflightArgs
    } else {
        Write-Host "5/5 Preflight ignorado por parametro."
    }

    Write-Host ""
    Write-Host "Atualizacao concluida."
} finally {
    Pop-Location
}
