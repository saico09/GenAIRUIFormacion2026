#Requires -Version 7
# PostgreSQL debe estar saludable y el perfil genai ya debe existir (puede estar detenido).
$ErrorActionPreference = 'Stop'
$repoDir = Split-Path -Parent $PSScriptRoot
$networkName = 'genai'
$postgresIp = '192.168.49.10'

Push-Location $repoDir
try {
    $networkJson = docker network inspect $networkName
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo leer la red genai; crea primero el perfil y comprueba Docker Desktop.' }
    $network = @($networkJson | ConvertFrom-Json -AsHashtable)[0]
    if ($network.Driver -ne 'bridge' -or '192.168.49.0/24' -notin @($network.IPAM.Config.Subnet)) {
        throw 'La red genai no usa el bridge 192.168.49.0/24 esperado; no se modifico ninguna conexion.'
    }

    $postgresIds = @(docker compose ps -q postgres)
    if ($LASTEXITCODE -ne 0 -or $postgresIds.Count -ne 1 -or [string]::IsNullOrWhiteSpace($postgresIds[0])) {
        throw 'Se necesita un PostgreSQL de Compose iniciado; ejecuta docker compose up -d --wait postgres.'
    }
    $postgresId = $postgresIds[0].Trim()
    foreach ($entry in $network.Containers.GetEnumerator()) {
        if (($entry.Value.IPv4Address -split '/')[0] -eq $postgresIp -and $entry.Key -ne $postgresId) {
            throw 'La IP 192.168.49.10 ya pertenece a otro contenedor; no se modifico ninguna conexion.'
        }
    }

    # Solo se leen las redes: no se imprimen variables ni credenciales del contenedor.
    $networksJson = docker inspect --format '{{json .NetworkSettings.Networks}}' $postgresId
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron consultar las redes de PostgreSQL.' }
    $networks = $networksJson | ConvertFrom-Json -AsHashtable
    if (-not $networks.ContainsKey($networkName)) {
        # La red original conserva prioridad 0; esta conexion no cambia la salida de PostgreSQL.
        docker network connect --ip $postgresIp --gw-priority=-1 --alias postgres-genai $networkName $postgresId
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo conectar PostgreSQL a la red genai.' }
        $networksJson = docker inspect --format '{{json .NetworkSettings.Networks}}' $postgresId
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo comprobar la conexion creada para PostgreSQL.' }
        $networks = $networksJson | ConvertFrom-Json -AsHashtable
    }

    $endpoint = $networks[$networkName]
    if ($endpoint.IPAddress -ne $postgresIp -or $endpoint.GwPriority -ne -1) {
        throw 'La conexion existente de PostgreSQL a genai no tiene IP 192.168.49.10 y prioridad -1; revisar sin desconectarla automaticamente.'
    }
    Write-Output 'PostgreSQL conectado directamente a Minikube: 192.168.49.10:5432.'
} finally {
    Pop-Location
}
