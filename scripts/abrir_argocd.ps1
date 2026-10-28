# Mantiene el port-forward local en segundo plano, sin ventana ni credenciales.
$ErrorActionPreference = 'Stop'
$repoDir = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $repoDir '.local'
$kubectlPath = Join-Path $localDir 'bin/kubectl.exe'
$pidFile = Join-Path $localDir 'argocd-port-forward.pid'
New-Item -ItemType Directory -Force -Path $localDir | Out-Null

function Test-ArgoEndpoint {
    try {
        # La excepcion TLS se limita al certificado local de este endpoint.
        $version = Invoke-RestMethod -Uri 'https://127.0.0.1:8443/api/version' -SkipCertificateCheck -TimeoutSec 2
        return $version.Version -match '^v[0-9]+\.[0-9]+\.[0-9]+'
    } catch { return $false }
}

$listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    if ($owner.ExecutablePath -ne $kubectlPath -or
        $owner.CommandLine -notmatch '(^|\s)--context=genai(\s|$)' -or
        $owner.CommandLine -notmatch '(^|\s)(-n\s+argocd|--namespace=argocd)(\s|$)' -or
        $owner.CommandLine -notmatch '(^|\s)svc/argocd-server(\s|$)' -or
        $owner.CommandLine -notmatch '(^|\s)8443:443(\s|$)' -or
        $owner.CommandLine -notmatch '(^|\s)--address=127\.0\.0\.1(\s|$)') {
        throw 'El puerto 8443 ya esta ocupado por otro proceso; no se modifico.'
    }
    if (Test-ArgoEndpoint) {
        $listener.OwningProcess | Set-Content -LiteralPath $pidFile -Encoding ascii
        Write-Output 'Argo CD ya tiene port-forward activo: https://localhost:8443'
        return
    }
    # El puerto puede seguir abierto despues de perder la conexion con el pod.
    Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
    Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue | Wait-Process -Timeout 5
    Write-Output 'El tunel anterior no responde por HTTPS; se abre otro hacia un pod disponible.'
}

$forward = Start-Process -FilePath $kubectlPath -ArgumentList @(
    '--context=genai', '-n', 'argocd', 'port-forward', 'svc/argocd-server',
    '8443:443', '--address=127.0.0.1'
) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localDir 'argocd-port-forward.out.log') -RedirectStandardError (Join-Path $localDir 'argocd-port-forward.err.log')
$forward.Id | Set-Content -LiteralPath $pidFile -Encoding ascii
$deadline = (Get-Date).AddSeconds(30)
do {
    $forward.Refresh()
    if ($forward.HasExited) { throw 'El port-forward termino; revisar .local/argocd-port-forward.err.log.' }
    if (Test-ArgoEndpoint) {
        Write-Output 'Argo CD disponible mediante port-forward: https://localhost:8443'
        return
    }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)
throw 'Argo CD no respondio por HTTPS en 30 segundos; revisar el log local.'
