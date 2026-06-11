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
    $knownPaths = @(
        (Join-Path $env:ProgramFiles "WiX Toolset v7.0\bin\wix.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "WiX Toolset v7.0\bin\wix.exe")
    )
    foreach ($path in $knownPaths) {
        if ($Names -contains (Split-Path -Leaf $path) -and (Test-Path $path)) { return $path }
    }
    return $null
}

function Invoke-CheckedCommand([string]$FilePath, [string[]]$Arguments) {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Comando falhou ($LASTEXITCODE): $FilePath $($Arguments -join ' ')"
    }
}

function Invoke-CodeSign([string]$Path) {
    $signtool = $env:PRINTBILLING_SIGNTOOL
    if (-not $signtool) { $signtool = Find-CommandPath @("signtool.exe") }
    if (-not (Test-Path $Path)) { return }

    $hasCertificateConfig = $env:PRINTBILLING_CERT_PFX -or $env:PRINTBILLING_CERT_THUMBPRINT
    if (-not $signtool) {
        if ($hasCertificateConfig) {
            throw "Configuracao de assinatura encontrada, mas signtool.exe nao foi localizado."
        }
        return
    }

    $timestamp = $env:PRINTBILLING_TIMESTAMP_URL
    if (-not $timestamp) { $timestamp = "http://timestamp.digicert.com" }

    if ($env:PRINTBILLING_CERT_PFX) {
        $args = @("sign", "/fd", "SHA256", "/tr", $timestamp, "/td", "SHA256", "/f", $env:PRINTBILLING_CERT_PFX)
        if ($env:PRINTBILLING_CERT_PASSWORD) { $args += @("/p", $env:PRINTBILLING_CERT_PASSWORD) }
        $args += $Path
        Invoke-CheckedCommand $signtool $args
        return
    }

    if ($env:PRINTBILLING_CERT_THUMBPRINT) {
        Invoke-CheckedCommand $signtool @("sign", "/fd", "SHA256", "/tr", $timestamp, "/td", "SHA256", "/sha1", $env:PRINTBILLING_CERT_THUMBPRINT, $Path)
    }
}

function Assert-PublishableFile([string]$Path) {
    if (-not (Test-Path $Path)) {
        throw "Artefato nao encontrado: $Path"
    }
    $item = Get-Item $Path
    if ($item.Length -le 0) {
        throw "Artefato vazio nao pode ser publicado: $Path"
    }
    return $item
}

function Get-SignatureInfo([string]$Path) {
    $signature = Get-AuthenticodeSignature -FilePath $Path
    return [ordered]@{
        signature_status = $signature.Status.ToString()
        signer_subject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { $null }
    }
}

function Get-FileEntry([string]$Kind, [string]$Path, [string]$ReleaseVersion) {
    $item = Assert-PublishableFile $Path
    $hash = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
    $signatureInfo = Get-SignatureInfo $Path
    return [ordered]@{
        kind = $Kind
        filename = Split-Path -Leaf $Path
        size_bytes = $item.Length
        sha256 = $hash
        signature_status = $signatureInfo.signature_status
        signer_subject = $signatureInfo.signer_subject
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
        Invoke-CheckedCommand $wix @("build", $wxs, "-d", "InstallerExe=$InstallerExe", "-d", "Version=$msiVersion", "-o", $msi)
        if (-not (Test-Path $msi)) { throw "WiX finalizou sem gerar MSI: $msi" }
        return $msi
    }

    $candle = Find-CommandPath @("candle.exe")
    $light = Find-CommandPath @("light.exe")
    if ($candle -and $light) {
        $obj = Join-Path $OutDir "PrintBillingAgent.wixobj"
        Invoke-CheckedCommand $candle @("-dInstallerExe=$InstallerExe", "-dVersion=$msiVersion", "-out", $obj, $wxs)
        Invoke-CheckedCommand $light @("-out", $msi, $obj)
        if (-not (Test-Path $msi)) { throw "WiX finalizou sem gerar MSI: $msi" }
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

Invoke-CheckedCommand $pyinstaller @("--clean", "--noconfirm", "--workpath", "build_release_agent", "--distpath", "dist_release_agent", "PrintBillingAgent.spec")

New-Item -ItemType Directory -Force -Path "installer_payload" | Out-Null
Copy-Item "dist_release_agent\PrintBillingAgent.exe" "installer_payload\PrintBillingAgent.exe" -Force
Copy-Item "config.json.example" "installer_payload\config.json.example" -Force

Invoke-CheckedCommand $pyinstaller @("--clean", "--noconfirm", "--onefile", "--name", "PrintBillingAgentInstaller", "--add-binary", "installer_payload\PrintBillingAgent.exe;.", "--add-data", "installer_payload\config.json.example;.", "agent_installer.py")

$agentExe = Join-Path $releaseDir "PrintBillingAgent.exe"
$installerExe = Join-Path $releaseDir "PrintBillingAgentInstaller.exe"
Copy-Item "dist_release_agent\PrintBillingAgent.exe" $agentExe -Force
Copy-Item "dist\PrintBillingAgentInstaller.exe" $installerExe -Force

Assert-PublishableFile $agentExe | Out-Null
Assert-PublishableFile $installerExe | Out-Null

Invoke-CodeSign $agentExe
Invoke-CodeSign $installerExe

$msiPath = Build-Msi -InstallerExe $installerExe -OutDir $releaseDir -ReleaseVersion $releaseVersion
if ($msiPath) {
    Assert-PublishableFile $msiPath | Out-Null
    Invoke-CodeSign $msiPath
}

$files = @()
$files += Get-FileEntry -Kind "agent" -Path $agentExe -ReleaseVersion $releaseVersion
$files += Get-FileEntry -Kind "installer" -Path $installerExe -ReleaseVersion $releaseVersion
if ($msiPath -and (Test-Path $msiPath)) { $files += Get-FileEntry -Kind "msi" -Path $msiPath -ReleaseVersion $releaseVersion }

$publishedAt = (Get-Date).ToUniversalTime().ToString("o")
$manifestPath = Join-Path $ReleaseRoot "manifest.json"
$existingVersions = @()
if (Test-Path $manifestPath) {
    try {
        $existingManifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
        $existingVersions = @($existingManifest.versions | Where-Object { $_.version -ne $releaseVersion })
    } catch {
        Write-Warning "Manifest existente nao pode ser lido e sera recriado: $manifestPath"
    }
}

$currentRelease = [ordered]@{
    version = $releaseVersion
    channel = $Channel
    published_at = $publishedAt
    notes = $Notes
    files = $files
}

$manifest = [ordered]@{
    generated_at = $publishedAt
    versions = @($currentRelease) + @($existingVersions)
}

$manifestJson = $manifest | ConvertTo-Json -Depth 10
$utf8NoBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
[System.IO.File]::WriteAllText($manifestPath, $manifestJson + [Environment]::NewLine, $utf8NoBom)

$sums = foreach ($file in $files) { "$($file.sha256)  $($file.filename)" }
$sums | Set-Content -Path (Join-Path $releaseDir "SHA256SUMS.txt") -Encoding ASCII

Write-Host "Release gerado em: $releaseDir"
Write-Host "Manifest: $manifestPath"
