# Abre FastAPI de Minikube en localhost:8002, sin ventana ni cambios en el contexto activo.
$ErrorActionPreference = 'Stop'
$repoDir = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $repoDir '.local'
$kubectlPath = Join-Path $localDir 'bin/kubectl.exe'
$pidFile = Join-Path $localDir 'fastapi-minikube-port-forward.pid'
New-Item -ItemType Directory -Force -Path $localDir | Out-Null

$listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    if ($owner.ExecutablePath -ne $kubectlPath -or $owner.CommandLine -notmatch '--context=genai' -or $owner.CommandLine -notmatch '--namespace=genai' -or $owner.CommandLine -notmatch 'svc/fastapi') {
        throw 'El puerto 8002 ya esta ocupado por otro proceso; no se modifico.'
    }
    $listener.OwningProcess | Set-Content -LiteralPath $pidFile -Encoding ascii
    Write-Output 'FastAPI ya tiene port-forward activo: http://localhost:8002'
    return
}

$forward = Start-Process -FilePath $kubectlPath -ArgumentList @(
    '--context=genai', '--namespace=genai', 'port-forward', 'svc/fastapi',
    '8002:8000', '--address=127.0.0.1'
) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localDir 'fastapi-minikube-port-forward.out.log') -RedirectStandardError (Join-Path $localDir 'fastapi-minikube-port-forward.err.log')
$forward.Id | Set-Content -LiteralPath $pidFile -Encoding ascii
$deadline = (Get-Date).AddSeconds(30)
do {
    $forward.Refresh()
    if ($forward.HasExited) { throw 'El port-forward termino; revisar .local/fastapi-minikube-port-forward.err.log.' }
    if (Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue) {
        Write-Output 'FastAPI disponible mediante port-forward: http://localhost:8002'
        return
    }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)
throw 'El port-forward no abrio el puerto 8002 en 30 segundos; revisar el log local.'
