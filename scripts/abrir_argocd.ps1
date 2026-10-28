# Mantiene el port-forward local en segundo plano, sin ventana ni credenciales.
$ErrorActionPreference = 'Stop'
$repoDir = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $repoDir '.local'
$kubectlPath = Join-Path $localDir 'bin/kubectl.exe'
$pidFile = Join-Path $localDir 'argocd-port-forward.pid'
New-Item -ItemType Directory -Force -Path $localDir | Out-Null

$listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    if ($owner.ExecutablePath -ne $kubectlPath -or $owner.CommandLine -notmatch '--context=genai' -or $owner.CommandLine -notmatch 'svc/argocd-server') {
        throw 'El puerto 8443 ya esta ocupado por otro proceso; no se modifico.'
    }
    $listener.OwningProcess | Set-Content -LiteralPath $pidFile -Encoding ascii
    Write-Output 'Argo CD ya tiene port-forward activo: https://localhost:8443'
    return
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
    if (Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue) {
        Write-Output 'Argo CD disponible mediante port-forward: https://localhost:8443'
        return
    }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)
throw 'El port-forward no abrio el puerto 8443 en 30 segundos; revisar el log local.'
