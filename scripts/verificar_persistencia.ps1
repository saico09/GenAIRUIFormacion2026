param(
    [ValidateSet('python-api', 'java-api')]
    [string]$Servicio = 'python-api'
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$puerto = if ($Servicio -eq 'python-api') { 8000 } else { 8080 }
$url = "http://localhost:$puerto/patients"
$antes = @(Invoke-RestMethod $url | ForEach-Object { $_ })
$ana = @($antes | Where-Object { $_.name -eq 'Ana Demo' -and $_.email -eq 'ana@example.com' })
if ($ana.Count -ne 1 -or $ana[0].birth_date -ne '1990-01-10') {
    throw 'Se necesita una Ana Demo original para comprobar persistencia.'
}

# restart no espera depends_on: primero recupera la base y después arranca la API.
docker compose restart postgres
if ($LASTEXITCODE -ne 0) { throw 'No se pudo reiniciar PostgreSQL.' }
docker compose up -d --wait --wait-timeout 60 postgres
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL no quedó saludable.' }
docker compose restart $Servicio
if ($LASTEXITCODE -ne 0) { throw 'No se pudo reiniciar la API.' }

$despues = $null
for ($intento = 0; $intento -lt 30; $intento++) {
    try {
        $despues = @(Invoke-RestMethod $url -TimeoutSec 3 | ForEach-Object { $_ })
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}
if ($null -eq $despues) { throw 'La API no responde después del reinicio.' }

# Compara en memoria sin imprimir datos que el usuario haya agregado.
$campos = @('id', 'name', 'birth_date', 'email')
$original = $antes | Sort-Object id | Select-Object $campos | ConvertTo-Json -Compress
$actual = $despues | Sort-Object id | Select-Object $campos | ConvertTo-Json -Compress
if ($original -cne $actual) { throw 'Las filas antes y después del reinicio difieren.' }
$anaDespues = Invoke-RestMethod "$url/$($ana[0].id)"
if (($ana[0] | Select-Object $campos | ConvertTo-Json -Compress) -cne
    ($anaDespues | Select-Object $campos | ConvertTo-Json -Compress)) {
    throw 'Los cuatro campos de Ana cambiaron.'
}
Write-Output "OK $Servicio : $($antes.Count) filas conservadas; Ana id=$($ana[0].id), cuatro campos originales; sin borrar pgdata."
