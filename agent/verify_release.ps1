param(
    [string]$ReleaseRoot = "",
    [string]$Version = "",
    [switch]$RequireSignature
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ReleaseRoot) { $ReleaseRoot = Join-Path $Root "releases" }

$manifestPath = Join-Path $ReleaseRoot "manifest.json"
if (-not (Test-Path $manifestPath)) {
    throw "Manifest nao encontrado: $manifestPath"
}

$manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
$versions = @($manifest.versions)
if ($Version) {
    $versions = @($versions | Where-Object { $_.version -eq $Version })
}
if ($versions.Count -eq 0) {
    throw "Nenhuma versao encontrada para validacao."
}

$failures = New-Object System.Collections.Generic.List[string]

foreach ($release in $versions) {
    foreach ($file in @($release.files)) {
        $path = Join-Path (Join-Path $ReleaseRoot $release.version) $file.filename
        if (-not (Test-Path $path)) {
            $failures.Add("Arquivo ausente: $path")
            continue
        }

        $hash = (Get-FileHash -Algorithm SHA256 -Path $path).Hash.ToLowerInvariant()
        if ($hash -ne $file.sha256) {
            $failures.Add("Hash divergente: $($file.filename)")
        }

        $size = (Get-Item $path).Length
        if ($file.size_bytes -and $size -ne [int64]$file.size_bytes) {
            $failures.Add("Tamanho divergente: $($file.filename)")
        }

        $signature = Get-AuthenticodeSignature -FilePath $path
        $manifestSignature = ""
        if ($null -ne $file.signature_status) {
            $manifestSignature = [string]$file.signature_status
        }
        if ($manifestSignature -and $manifestSignature -ne $signature.Status.ToString()) {
            $failures.Add("Assinatura divergente no manifest: $($file.filename)")
        }
        if ($RequireSignature -and $signature.Status -ne "Valid") {
            $failures.Add("Arquivo nao assinado/assinatura invalida: $($file.filename) ($($signature.Status))")
        }
    }
}

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) {
        Write-Error $failure
    }
    throw "Validacao de release falhou."
}

Write-Host "Release validado com sucesso: $ReleaseRoot"
