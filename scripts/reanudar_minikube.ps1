#Requires -Version 7
# Reanuda el perfil principal existente; no instala ni cambia el despliegue de Git.
$ErrorActionPreference = 'Stop'
$repoDir = Split-Path -Parent $PSScriptRoot
$minikubePath = Join-Path $repoDir '.local/bin/minikube.exe'
$kubectlPath = Join-Path $repoDir '.local/bin/kubectl.exe'
foreach ($toolPath in @($minikubePath, $kubectlPath)) {
    if (-not (Test-Path -LiteralPath $toolPath -PathType Leaf)) {
        throw 'Faltan las herramientas locales; sigue Preparar Minikube por primera vez en GUIA.md.'
    }
}

$previousPath = $env:PATH
Push-Location $repoDir
try {
    # Tambien los subprocesos de Minikube usan kubectl local; no cambia el PATH del equipo.
    $env:PATH = (Join-Path $repoDir '.local/bin') + [IO.Path]::PathSeparator + $previousPath
    $profilesJson = & $minikubePath profile list --output=json
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron consultar los perfiles de Minikube.' }
    $profiles = $profilesJson | ConvertFrom-Json
    if (-not (@($profiles.valid) | Where-Object { $_.Name -eq 'genai' })) {
        throw 'El perfil genai no existe o no es valido; sigue la preparacion inicial de GUIA.md.'
    }

    Write-Output '1/5 Esperando PostgreSQL de Compose...'
    docker compose up -d --wait --wait-timeout 120 postgres
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL no quedo saludable; revisar docker compose logs postgres.' }
    & (Join-Path $PSScriptRoot 'conectar_postgres_minikube.ps1')

    Write-Output '2/5 Reanudando el perfil genai...'
    & $minikubePath start --profile=genai --keep-context --wait=all --wait-timeout=6m
    if ($LASTEXITCODE -ne 0) { throw 'Minikube no termino de arrancar; no se abrieron tuneles.' }
    $historyMount = & (Join-Path $PSScriptRoot 'montar_historias_minikube.ps1')

    $deploymentJson = & $kubectlPath --context=genai -n genai get deployment fastapi -o json
    if ($LASTEXITCODE -ne 0) { throw 'No se encontro el Deployment fastapi; revisar la Application de Argo CD.' }
    $deployment = $deploymentJson | ConvertFrom-Json
    $container = @($deployment.spec.template.spec.containers | Where-Object { $_.name -eq 'fastapi' })[0]
    if ($null -eq $container) { throw 'El Deployment no contiene el contenedor fastapi.' }

    Write-Output '3/5 Comprobando SQL desde un pod temporal del perfil...'
    $podName = 'postgres-reanudar-' + [guid]::NewGuid().ToString('N')
    # Usa la imagen y configuracion desplegadas, incluidos los Secret refs; no imprime sus valores.
    $sqlContainer = @{
        name = 'postgres-check'; image = $container.image
        imagePullPolicy = $container.imagePullPolicy
        command = @('python', '-c')
        args = @(@'
import os
import time
from pathlib import Path
import tempfile
import psycopg

marker = os.environ.get("HISTORY_SHARED_MARKER")
if marker:
    assert Path(marker).read_text().strip() == "genai-historias-v1"
    directory = Path(os.environ["HISTORY_DIR"])
    descriptor, temporary = tempfile.mkstemp(prefix=".mount-probe-", dir=directory)
    final = Path(temporary + ".result")
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write("mount-ok")
        os.replace(temporary, final)
        assert final.read_text() == "mount-ok"
    finally:
        Path(temporary).unlink(missing_ok=True)
        final.unlink(missing_ok=True)

deadline = time.monotonic() + 120
while True:
    try:
        with psycopg.connect(
            host=os.environ["POSTGRES_HOST"],
            port=os.environ.get("POSTGRES_PORT", "5432"),
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            connect_timeout=5,
        ) as connection:
            value = connection.execute("SELECT 1").fetchone()[0]
        if value != 1:
            raise SystemExit("SELECT 1 devolvio un resultado inesperado.")
        print(1)
        break
    except psycopg.Error:
        if time.monotonic() >= deadline:
            raise SystemExit("No se pudo conectar a PostgreSQL; revisar host, puerto y Secret del Deployment.") from None
        time.sleep(2)
'@)
    }
    if ($container.env) { $sqlContainer.env = $container.env }
    if ($container.envFrom) { $sqlContainer.envFrom = $container.envFrom }
    if ($container.volumeMounts) { $sqlContainer.volumeMounts = $container.volumeMounts }
    $pod = @{
        apiVersion = 'v1'; kind = 'Pod'
        metadata = @{ name = $podName; namespace = 'genai' }
        spec = @{ restartPolicy = 'Never'; activeDeadlineSeconds = 150; containers = @($sqlContainer) }
    }
    if ($deployment.spec.template.spec.volumes) { $pod.spec.volumes = $deployment.spec.template.spec.volumes }
    if ($deployment.spec.template.spec.securityContext) { $pod.spec.securityContext = $deployment.spec.template.spec.securityContext }
    try {
        $pod | ConvertTo-Json -Depth 20 -Compress | & $kubectlPath --context=genai -n genai create -f -
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el pod temporal de comprobacion SQL.' }
        & $kubectlPath --context=genai -n genai wait '--for=jsonpath={.status.phase}=Succeeded' "pod/$podName" --timeout=160s
        if ($LASTEXITCODE -ne 0) {
            throw 'El pod no pudo comprobar SQL; revisar la conexion PostgreSQL del Deployment. No se abrieron tuneles.'
        }
        $sqlResult = & $kubectlPath --context=genai -n genai logs "pod/$podName"
        if ($LASTEXITCODE -ne 0 -or ($sqlResult -join "`n").Trim() -ne '1') {
            throw 'No se obtuvo SELECT 1 = 1 desde el perfil.'
        }
        Write-Output 'SQL desde Minikube: SELECT 1 = 1.'
    } finally {
        # Nombre nuevo por ejecucion: solo se elimina el pod que este comando acaba de crear.
        & $kubectlPath --context=genai -n genai delete pod $podName --ignore-not-found --wait=true --timeout=20s
        if ($LASTEXITCODE -ne 0) { Write-Warning "No se pudo limpiar el pod temporal $podName." }
    }

    Write-Output '4/5 Esperando las replicas deseadas de FastAPI...'
    if (-not $historyMount.Reused) {
        # Un pod anterior puede conservar el bind de un montaje perdido. No cambia el chart ni las replicas.
        & $kubectlPath --context=genai -n genai rollout restart deployment/fastapi
        if ($LASTEXITCODE -ne 0) { throw 'No se pudieron renovar los pods tras recuperar el montaje.' }
    }
    & $kubectlPath --context=genai -n genai rollout status deployment/fastapi --timeout=300s
    if ($LASTEXITCODE -ne 0) { throw 'FastAPI no quedo Ready; revisar sus eventos y logs antes de abrir tuneles.' }
    $readyJson = & $kubectlPath --context=genai -n genai get deployment fastapi -o json
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo comprobar el numero de replicas listas.' }
    $ready = $readyJson | ConvertFrom-Json
    if ($ready.spec.replicas -lt 1 -or $ready.status.readyReplicas -ne $ready.spec.replicas) {
        throw 'Las replicas Ready no coinciden con las deseadas; no se abrieron tuneles.'
    }

    Write-Output '5/5 Abriendo los accesos locales...'
    & $kubectlPath --context=genai -n argocd rollout status deployment/argocd-server --timeout=180s
    if ($LASTEXITCODE -ne 0) { throw 'Argo CD no quedo disponible; revisar su Deployment.' }
    & (Join-Path $PSScriptRoot 'abrir_argocd.ps1')
    & (Join-Path $PSScriptRoot 'abrir_fastapi_minikube.ps1')
    $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8002/patients' -TimeoutSec 10
    if ($response.StatusCode -ne 200) { throw 'El acceso al CRUD no devolvio HTTP 200.' }
    Write-Output "OK: $($ready.status.readyReplicas) replicas Ready y GET /patients = 200."
    Write-Output 'CRUD: http://localhost:8002/patients | Argo CD: https://localhost:8443'
} finally {
    $env:PATH = $previousPath
    Pop-Location
}
