# Descarga las herramientas fijadas para Windows x64; no inicia ningun cluster.
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
    throw 'Este script prepara binarios para Windows x64.'
}

$repoDir = Split-Path -Parent $PSScriptRoot
$binDir = Join-Path $repoDir '.local/bin'
New-Item -ItemType Directory -Force -Path $binDir | Out-Null

# SHA-256 publicados por los proyectos oficiales para estas versiones exactas.
$downloads = @(
    @{
        name = 'minikube'; version = '1.39.0'; file = 'minikube.exe'
        url = 'https://github.com/kubernetes/minikube/releases/download/v1.39.0/minikube-windows-amd64.exe'
        checksum_url = 'https://github.com/kubernetes/minikube/releases/download/v1.39.0/minikube-windows-amd64.exe.sha256'
        sha256 = '776386465ded2cf610ae397fe302de32c44d12134b5ce7ce98ab05bd7713b360'
    },
    @{
        name = 'helm'; version = '4.3.1'; file = 'helm-v4.3.1-windows-amd64.zip'
        url = 'https://get.helm.sh/helm-v4.3.1-windows-amd64.zip'
        checksum_url = 'https://get.helm.sh/helm-v4.3.1-windows-amd64.zip.sha256sum'
        sha256 = 'fcfd7b796dcf0f225abc40b5636a3b01f55f3de2fb1dfb18475df94e62c14112'
    },
    @{
        name = 'kubectl'; version = '1.36.6'; file = 'kubectl.exe'
        url = 'https://dl.k8s.io/release/v1.36.6/bin/windows/amd64/kubectl.exe'
        checksum_url = 'https://dl.k8s.io/release/v1.36.6/bin/windows/amd64/kubectl.exe.sha256'
        sha256 = '2bc0fbea066016c62cfef307108c303c2f796420d4a5dfc844de6e25d4bc47e0'
    }
)

foreach ($item in $downloads) {
    $target = Join-Path $binDir $item.file
    $valid = (Test-Path -LiteralPath $target) -and ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -eq $item.sha256)
    if (-not $valid) {
        $temporary = $target + '.download'
        Invoke-WebRequest -Uri $item.url -OutFile $temporary -TimeoutSec 300 -UseBasicParsing
        $actual = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $item.sha256) { throw "SHA-256 incorrecto para $($item.name); no se instalara." }
        Move-Item -LiteralPath $temporary -Destination $target -Force
    }
    Write-Output "$($item.name) $($item.version): SHA-256 correcto"
}

# Extrae solo el ejecutable esperado del ZIP ya verificado.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead((Join-Path $binDir 'helm-v4.3.1-windows-amd64.zip'))
try {
    $entry = $archive.GetEntry('windows-amd64/helm.exe')
    if ($null -eq $entry) { throw 'El ZIP de Helm no contiene windows-amd64/helm.exe.' }
    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $binDir 'helm.exe'), $true)
} finally {
    $archive.Dispose()
}

$minikubeVersion = & (Join-Path $binDir 'minikube.exe') version --short
if ($LASTEXITCODE -ne 0 -or $minikubeVersion.Trim() -ne 'v1.39.0') { throw 'Version inesperada de Minikube.' }
$helmVersion = & (Join-Path $binDir 'helm.exe') version --short
if ($LASTEXITCODE -ne 0 -or $helmVersion -notmatch '^v4\.3\.1(?:\+|$)') { throw 'Version inesperada de Helm.' }
$kubectlVersion = & (Join-Path $binDir 'kubectl.exe') version --client -o json
if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar kubectl.' }
$kubectlData = $kubectlVersion | ConvertFrom-Json
if ($kubectlData.clientVersion.gitVersion -ne 'v1.36.6') { throw 'Version inesperada de kubectl.' }

$evidenceDir = Join-Path $repoDir 'evidencias/s09'
New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
@{
    checked_at = [DateTime]::UtcNow.ToString('o')
    phase = 'Preparacion de binarios; este script no inicia el cluster'
    platform = 'windows/amd64'
    downloads = $downloads
    versions = @{ minikube = $minikubeVersion.Trim(); helm = $helmVersion.Trim(); kubectl = $kubectlData.clientVersion.gitVersion }
    executable_sha256 = @{
        minikube = (Get-FileHash -LiteralPath (Join-Path $binDir 'minikube.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
        helm = (Get-FileHash -LiteralPath (Join-Path $binDir 'helm.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
        kubectl = (Get-FileHash -LiteralPath (Join-Path $binDir 'kubectl.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
    }
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidenceDir '039-herramientas.json') -Encoding utf8
Write-Output "Herramientas listas en $binDir. No se cambio el PATH ni se inicio Minikube."
