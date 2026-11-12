#Requires -Version 7
# Ejecutar desde PowerShell 7. No llama a Docker: la funcion local intercepta sus comandos.
param([string]$OutputPath = (Join-Path $PSScriptRoot '../.local/verificaciones/conexion-minikube.json'))
$ErrorActionPreference = 'Stop'
$helperPath = Join-Path $PSScriptRoot 'conectar_postgres_minikube.ps1'
$resultPath = [IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Force -Path (Split-Path $resultPath) | Out-Null
$global:mockPgId = 'a' * 64

function global:docker {
    $global:LASTEXITCODE = 0
    $command = $args -join ' '
    $global:mockCalls.Add($command)
    if ($command -eq 'network inspect genai') {
        if ($global:mockScenario -eq 'network-error') { $global:LASTEXITCODE = 1; return }
        $containers = @{ ('b' * 64) = @{IPv4Address='192.168.49.2/24'} }
        if ($global:mockAttached) { $containers[$global:mockPgId] = @{IPv4Address='192.168.49.10/24'} }
        if ($global:mockScenario -eq 'ip-clash') { $containers[('c' * 64)] = @{IPv4Address='192.168.49.10/24'} }
        $subnet = if ($global:mockScenario -eq 'wrong-subnet') {'172.18.0.0/16'} else {'192.168.49.0/24'}
        # Array de un solo objeto, igual que docker network inspect.
        return '[' + (@{Driver='bridge';IPAM=@{Config=@(@{Subnet=$subnet})};Containers=$containers} | ConvertTo-Json -Depth 5 -Compress) + ']'
    }
    if ($command -eq 'compose ps -q postgres') {
        if ($global:mockScenario -eq 'no-postgres') { return }
        return $global:mockPgId
    }
    if ($command -eq "inspect --format {{json .NetworkSettings.Networks}} $global:mockPgId") {
        $networks = @{genairuiformacion2026_default=@{IPAddress='172.22.0.3';GwPriority=0}}
        if ($global:mockAttached) {
            $priority = if ($global:mockScenario -eq 'wrong-priority') {0} else {-1}
            $networks.genai = @{IPAddress='192.168.49.10';GwPriority=$priority}
        }
        return $networks | ConvertTo-Json -Depth 4 -Compress
    }
    if ($command -eq "network connect --ip 192.168.49.10 --gw-priority=-1 --alias postgres-genai genai $global:mockPgId") {
        if ($global:mockScenario -eq 'connect-error') { $global:LASTEXITCODE = 1; return }
        $global:mockAttached = $true
        return
    }
    throw "Comando inesperado del mock: $command"
}

$cases = @(
    @{name='new';error=$null;connections=1}
    @{name='existing';error=$null;connections=0}
    @{name='wrong-subnet';error='La red genai no usa';connections=0}
    @{name='ip-clash';error='La IP 192.168.49.10 ya pertenece';connections=0}
    @{name='wrong-priority';error='La conexion existente de PostgreSQL';connections=0}
    @{name='no-postgres';error='Se necesita un PostgreSQL';connections=0}
    @{name='network-error';error='No se pudo leer la red genai';connections=0}
    @{name='connect-error';error='No se pudo conectar PostgreSQL';connections=1}
)
$results = [Collections.Generic.List[object]]::new()
try {
    foreach ($case in $cases) {
        $global:mockScenario = $case.name
        $global:mockCalls = [Collections.Generic.List[string]]::new()
        $global:mockAttached = $case.name -in @('existing','wrong-priority')
        $observedError = $null
        $helperOutput = @()
        try { $helperOutput = @(& $helperPath) } catch { $observedError = $_.Exception.Message }
        $connectCount = @($global:mockCalls | Where-Object { $_.StartsWith('network connect ') }).Count
        $errorMatches = if ($null -eq $case.error) { $null -eq $observedError } else { $observedError -like "$($case.error)*" }
        $passed = $errorMatches -and $connectCount -eq $case.connections
        $results.Add([ordered]@{
            case = $case.name
            passed = $passed
            expected_error_prefix = $case.error
            observed_error = $observedError
            expected_connections = $case.connections
            observed_connections = $connectCount
            helper_output = $helperOutput
            intercepted_commands = @($global:mockCalls)
        })
        Write-Output "$($case.name): $(if ($passed) {'PASS'} else {'FAIL'})"
    }
} finally {
    Remove-Item Function:\docker
}

$report = [ordered]@{
    executed_at_utc = [DateTime]::UtcNow.ToString('o')
    powershell = $PSVersionTable.PSVersion.ToString()
    helper = 'scripts/conectar_postgres_minikube.ps1'
    helper_sha256 = (Get-FileHash -LiteralPath $helperPath -Algorithm SHA256).Hash.ToLowerInvariant()
    mode = 'isolated_mock'
    real_docker_invoked = $false
    total = $results.Count
    passed = @($results | Where-Object passed).Count
    cases = @($results)
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resultPath -Encoding utf8
if ($report.passed -ne $report.total) { throw "Fallaron pruebas aisladas; revisar $resultPath" }
Write-Output "OK: $($report.passed)/$($report.total), sin Docker real."
