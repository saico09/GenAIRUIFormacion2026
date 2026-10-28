# Lee el .env local y envia el Secret por stdin; no guarda ni imprime credenciales.
$ErrorActionPreference = 'Stop'
$repoDir = Split-Path -Parent $PSScriptRoot
$kubectlPath = Join-Path $repoDir '.local/bin/kubectl.exe'
$settings = @{}
foreach ($line in Get-Content -LiteralPath (Join-Path $repoDir '.env')) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $value = $Matches[2].Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $settings[$Matches[1]] = $value
    }
}
foreach ($key in @('POSTGRES_USER', 'POSTGRES_PASSWORD')) {
    if (-not $settings.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($settings[$key])) {
        throw "Falta $key en .env."
    }
}
if ($settings['POSTGRES_DB'] -ne 'genai') { throw 'El chart de esta practica espera POSTGRES_DB=genai.' }

$existing = & $kubectlPath --context=genai get namespace genai --ignore-not-found -o name
if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar el namespace genai.' }
if (-not $existing) {
    & $kubectlPath --context=genai create namespace genai
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el namespace genai.' }
}

$secret = @{
    apiVersion = 'v1'; kind = 'Secret'; type = 'Opaque'
    metadata = @{ name = 'genai-postgres'; namespace = 'genai' }
    data = @{
        POSTGRES_USER = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($settings['POSTGRES_USER']))
        POSTGRES_PASSWORD = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($settings['POSTGRES_PASSWORD']))
    }
}
# Server-side apply evita copiar el contenido a una anotacion last-applied-configuration.
$secret | ConvertTo-Json -Depth 4 -Compress | & $kubectlPath --context=genai apply --server-side --field-manager=genai-local -f -
if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear o actualizar genai-postgres.' }
Write-Output 'Secret genai-postgres listo en namespace genai; credenciales sin imprimir.'
