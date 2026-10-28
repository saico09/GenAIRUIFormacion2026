# Instala Argo CD fijado en el perfil genai; no crea Applications ni muestra claves.
$ErrorActionPreference = 'Stop'
$repoDir = Split-Path -Parent $PSScriptRoot
$kubectlPath = Join-Path $repoDir '.local/bin/kubectl.exe'
$manifestPath = Join-Path $repoDir '.local/argocd-install-v3.5.6.yaml'
$manifestUrl = 'https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.6/manifests/install.yaml'
$manifestHash = '846c644bc81ce5557dd9048757a9c7353378f25c5eb811c77d32a9e907823599'
$evidenceDir = Join-Path $repoDir 'evidencias/s09'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $manifestPath), $evidenceDir | Out-Null

if (-not (Test-Path -LiteralPath $manifestPath)) {
    Invoke-WebRequest -Uri $manifestUrl -OutFile $manifestPath -TimeoutSec 90 -UseBasicParsing
}
if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifestHash) {
    throw 'El manifiesto de Argo CD no coincide con el SHA-256 verificado; no se aplicara.'
}
$existing = & $kubectlPath --context=genai get namespace argocd --ignore-not-found -o name
if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar el namespace argocd.' }
if (-not $existing) {
    & $kubectlPath --context=genai create namespace argocd
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el namespace argocd.' }
}
& $kubectlPath --context=genai -n argocd apply --server-side --field-manager=genai-argocd -f $manifestPath
if ($LASTEXITCODE -ne 0) { throw 'No se pudo aplicar Argo CD; revisar el error sin forzar conflictos.' }
& $kubectlPath --context=genai -n argocd wait --for=condition=Available deployment --all --timeout=360s
if ($LASTEXITCODE -ne 0) { throw 'No todos los deployments de Argo CD quedaron Available.' }
& $kubectlPath --context=genai -n argocd rollout status statefulset/argocd-application-controller --timeout=360s
if ($LASTEXITCODE -ne 0) { throw 'El controlador de Argo CD no quedo Ready.' }
& $kubectlPath --context=genai -n argocd wait --for=condition=Ready pod --all --timeout=120s
if ($LASTEXITCODE -ne 0) { throw 'Quedan pods de Argo CD sin Ready.' }

$version = & $kubectlPath --context=genai -n argocd exec deployment/argocd-server -- argocd version --client --short
if ($LASTEXITCODE -ne 0 -or ($version -join ' ') -notmatch 'v3\.5\.6') { throw 'La version ejecutada de Argo CD no coincide.' }
@{
    checked_at = [DateTime]::UtcNow.ToString('o')
    context = 'genai'; namespace = 'argocd'; version = ($version -join "`n")
    manifest_url = $manifestUrl; manifest_sha256 = $manifestHash
    server_side_apply = $true; force_conflicts = $false
    deployments_available = $true; controller_ready = $true; pods_ready = $true
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $evidenceDir '041-instalacion.json') -Encoding utf8
& $kubectlPath --context=genai -n argocd get deployment,statefulset,pod -o wide |
    Tee-Object -FilePath (Join-Path $evidenceDir '041-componentes.txt')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo registrar el estado final de Argo CD.' }
Write-Output 'Argo CD listo. No se crearon Applications ni se leyeron claves.'
