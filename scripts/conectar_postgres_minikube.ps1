#Requires -Version 7
param([Alias('Profile')][ValidatePattern('^[a-z0-9][a-z0-9-]*$')][string]$ProfileName = 'genai')
# Conecta solo el PostgreSQL de este Compose a la red propia del perfil; conserva sus otras redes.
$ErrorActionPreference = 'Stop'
$repoDir = Split-Path -Parent $PSScriptRoot
$networkName = $ProfileName

Push-Location $repoDir
try {
    $networkJson = docker network inspect $networkName
    if ($LASTEXITCODE -ne 0) { throw "No se pudo leer la red $ProfileName; crea primero ese perfil de Minikube." }
    $network = @($networkJson | ConvertFrom-Json -AsHashtable)[0]
    if ($network.Driver -ne 'bridge' -or
        $network.Labels['created_by.minikube.sigs.k8s.io'] -ne 'true' -or
        $network.Labels['name.minikube.sigs.k8s.io'] -ne $ProfileName) {
        throw "La red $ProfileName no es el bridge propio de Minikube; no se modifico ninguna conexion."
    }
    $subnets = @($network.IPAM.Config | Where-Object { $_.Subnet -match '^([0-9]{1,3}\.){3}0/24$' })
    if ($subnets.Count -ne 1) { throw 'Se esperaba una sola subred IPv4 /24 de Minikube; no se modifico ninguna conexion.' }
    $networkAddress = [Net.IPAddress]::Parse(($subnets[0].Subnet -split '/')[0])
    $octets = $networkAddress.ToString().Split('.')
    $postgresIp = ($octets[0..2] -join '.') + '.10'
    if ($postgresIp -eq $subnets[0].Gateway) { throw 'La direccion reservada coincide con la puerta de enlace.' }

    # Incluso detenido, el nodo conserva su red e IP reservada en Docker.
    $nodeJson = docker inspect --format '{{json .NetworkSettings.Networks}}' $ProfileName
    if ($LASTEXITCODE -ne 0) { throw "No se encontro el nodo Docker del perfil $ProfileName." }
    $nodeNetworks = $nodeJson | ConvertFrom-Json -AsHashtable
    if (-not $nodeNetworks.ContainsKey($ProfileName) -or $nodeNetworks[$ProfileName].NetworkID -ne $network.Id) {
        throw 'El nodo no pertenece a la red del perfil; no se modifico ninguna conexion.'
    }
    if ($postgresIp -in @($nodeNetworks[$ProfileName].IPAddress, $nodeNetworks[$ProfileName].IPAMConfig.IPv4Address)) {
        throw 'La direccion de PostgreSQL coincide con la del nodo; no se modifico ninguna conexion.'
    }

    $postgresIds = @(docker compose ps -q postgres)
    if ($LASTEXITCODE -ne 0 -or $postgresIds.Count -ne 1 -or [string]::IsNullOrWhiteSpace($postgresIds[0])) {
        throw 'Se necesita un PostgreSQL de Compose iniciado; ejecuta docker compose up -d --wait postgres.'
    }
    $postgresId = $postgresIds[0].Trim()
    foreach ($entry in $network.Containers.GetEnumerator()) {
        if (($entry.Value.IPv4Address -split '/')[0] -eq $postgresIp -and $entry.Key -ne $postgresId) {
            throw "La IP $postgresIp ya pertenece a otro contenedor; no se modifico ninguna conexion."
        }
    }

    # Solo se leen las redes: no se imprimen variables ni credenciales del contenedor.
    $networksJson = docker inspect --format '{{json .NetworkSettings.Networks}}' $postgresId
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron consultar las redes de PostgreSQL.' }
    $networks = $networksJson | ConvertFrom-Json -AsHashtable
    if (-not $networks.ContainsKey($networkName)) {
        # La red original conserva prioridad 0; esta conexion no cambia la salida de PostgreSQL.
        docker network connect --ip $postgresIp --gw-priority=-1 --alias "postgres-$ProfileName" $networkName $postgresId
        if ($LASTEXITCODE -ne 0) { throw "No se pudo conectar PostgreSQL a la red $ProfileName." }
        $networksJson = docker inspect --format '{{json .NetworkSettings.Networks}}' $postgresId
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo comprobar la conexion creada para PostgreSQL.' }
        $networks = $networksJson | ConvertFrom-Json -AsHashtable
    }

    $endpoint = $networks[$networkName]
    if ($endpoint.IPAddress -ne $postgresIp -or $endpoint.GwPriority -ne -1) {
        throw "La conexion existente a $ProfileName no usa $postgresIp y prioridad -1; revisar sin desconectarla automaticamente."
    }
    Write-Host "PostgreSQL conectado directamente a ${ProfileName}: ${postgresIp}:5432."
    [pscustomobject]@{ Profile = $ProfileName; Network = $ProfileName; Address = $postgresIp; Port = 5432 }
} finally {
    Pop-Location
}

