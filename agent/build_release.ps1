param(
    [string]$Version = "",
    [string]$Channel = "stable",
    [string]$Notes = "",
    [string]$ReleaseRoot = "",
    [switch]$SkipMsi
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Get-AgentVersion {
    if ($Version) { return $Version }
    $python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) { $python = "python" }
    return (& $python -c "from version import AGENT_VERSION; print(AGENT_VERSION)").Trim()
}

function Normalize-MsiVersion([string]$InputVersion) {
    $parts = ($InputVersion -replace "[^0-9.]", "").Split(".", [System.StringSplitOptions]::RemoveEmptyEntries)
    while ($parts.Count -lt 3) { $parts += "0" }
    return ($parts[0..2] -join ".")
}

function Find-CommandPath([string[]]$Names) {
    foreach ($name in $Names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Invoke-CodeSign([string]$Path) {
    $signtool = $env:PRINTBILLING_SIGNTOOL
    if (-not $signtool) { $signtool = Find-CommandPath @("signtool.exe") }
    if (-not $signtool -or -not (Test-Path $Path)) { return }

    $timestamp = $env:PRINTBILLING_TIMESTAMP_URL
    if (-not $timestamp) { $timestamp = "http://timestamp.digicert.com" }

    if ($env:PRINTBILLING_CERT_PFX) {
        $args = @("sign", "/fd", "SHA256", "/tr", $timestamp, "/td", "SHA256", "/f", $env:PRINTBILLING_CERT_PFX)
        if ($env:PRINTBILLING_CERT_PASSWORD) { $args += @("/p", $env:PRINTBILLING_CERT_PASSWORD) }
        $args += $Path
        & $signtool @args
        return
    }

    if ($env:PRINTBILLING_CERT_THUMBPRINT) {
        & $signtool sign /fd SHA256 /tr $timestamp /td SHA256 /sha1 $env:PRINTBILLING_CERT_THUMBPRINT $Path
    }
}

function Get-FileEntry([string]$Kind, [string]$Path, [string]$ReleaseVersion) {
    $hash = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
    return [ordered]@{
        kind = $Kind
        filename = Split-Path -Leaf $Path
        size_bytes = (Get-Item $Path).Length
        sha256 = $hash
        download_url = "/agent/releases/$ReleaseVersion/download?filename=$(Split-Path -Leaf $Path)"
    }
}

function Build-Msi([string]$InstallerExe, [string]$OutDir, [string]$ReleaseVersion) {
    if ($SkipMsi) { return $null }

    $wix = Find-CommandPath @("wix.exe")
    $wxs = Join-Path $Root "installer.wxs"
    $msi = Join-Path $OutDir "PrintBillingAgent-$ReleaseVersion.msi"
    $msiVersion = Normalize-MsiVersion $ReleaseVersion
    if ($wix) {
        & $wix build $wxs -d InstallerExe="$InstallerExe" -d Version="$msiVersion" -o $msi
        return $msi
    }

    $candle = Find-CommandPath @("candle.exe")
    $light = Find-CommandPath @("light.exe")
    if ($candle -and $light) {
        $obj = Join-Path $OutDir "PrintBillingAgent.wixobj"
        & $candle -dInstallerExe="$InstallerExe" -dVersion="$msiVersion" -out $obj $wxs
        & $light -out $msi $obj
        return $msi
    }

    Write-Warning "WiX nao encontrado. MSI nao foi gerado. Instale WiX Toolset para gerar .msi."
    return $null
}

$releaseVersion = Get-AgentVersion
if (-not $ReleaseRoot) { $ReleaseRoot = Join-Path $Root "releases" }
$releaseDir = Join-Path $ReleaseRoot $releaseVersion
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$pyinstaller = Join-Path $Root ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $pyinstaller)) { throw "PyInstaller nao encontrado em $pyinstaller" }

& $pyinstaller --clean --noconfirm --workpath "build_release_agent" --distpath "dist_release_agent" "PrintBillingAgent.spec"

New-Item -ItemType Directory -Force -Path "installer_payload" | Out-Null
Copy-Item "dist_release_agent\PrintBillingAgent.exe" "installer_payload\PrintBillingAgent.exe" -Force
Copy-Item "config.json.example" "installer_payload\config.json.example" -Force

& $pyinstaller --clean --noconfirm --onefile --name "PrintBillingAgentInstaller" --add-binary "installer_payload\PrintBillingAgent.exe;." --add-data "installer_payload\config.json.example;." "agent_installer.py"

$agentExe = Join-Path $releaseDir "PrintBillingAgent.exe"
$installerExe = Join-Path $releaseDir "PrintBillingAgentInstaller.exe"
Copy-Item "dist_release_agent\PrintBillingAgent.exe" $agentExe -Force
Copy-Item "dist\PrintBillingAgentInstaller.exe" $installerExe -Force

Invoke-CodeSign $agentExe
Invoke-CodeSign $installerExe

$msiPath = Build-Msi -InstallerExe $installerExe -OutDir $releaseDir -ReleaseVersion $releaseVersion
if ($msiPath) { Invoke-CodeSign $msiPath }

$files = @()
$files += Get-FileEntry -Kind "agent" -Path $agentExe -ReleaseVersion $releaseVersion
$files += Get-FileEntry -Kind "installer" -Path $installerExe -ReleaseVersion $releaseVersion
if ($msiPath -and (Test-Path $msiPath)) { $files += Get-FileEntry -Kind "msi" -Path $msiPath -ReleaseVersion $releaseVersion }

$publishedAt = (Get-Date).ToUniversalTime().ToString("o")
$manifest = [ordered]@{
    generated_at = $publishedAt
    versions = @(
        [ordered]@{
            version = $releaseVersion
            channel = $Channel
            published_at = $publishedAt
            notes = $Notes
            files = $files
        }
    )
}

$manifestPath = Join-Path $ReleaseRoot "manifest.json"
$manifest | ConvertTo-Json -Depth 10 | Set-Content -Path $manifestPath -Encoding UTF8

$sums = foreach ($file in $files) { "$($file.sha256)  $($file.filename)" }
$sums | Set-Content -Path (Join-Path $releaseDir "SHA256SUMS.txt") -Encoding ASCII

Write-Host "Release gerado em: $releaseDir"
Write-Host "Manifest: $manifestPath"
