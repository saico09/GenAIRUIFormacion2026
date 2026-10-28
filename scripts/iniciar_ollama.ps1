$ErrorActionPreference = 'Stop'
$ollamaExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
if (-not (Test-Path -LiteralPath $ollamaExe)) {
    throw "Instala Ollama para Windows antes de continuar: https://ollama.com/download/windows"
}
try {
    $version = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
    Write-Output "Ollama $($version.version) ya responde en localhost:11434"
    return
} catch { }

$logDir = Join-Path $env:LOCALAPPDATA 'Ollama\genai'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
# Solo afectan este proceso y el servidor hijo, no la configuración global de Windows.
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_NO_CLOUD = '1'
$server = Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDir 'stdout.log') `
    -RedirectStandardError (Join-Path $logDir 'stderr.log')
for ($i = 0; $i -lt 20; $i++) {
    try {
        $version = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
        Write-Output "Ollama $($version.version) iniciado; PID $($server.Id); logs en $logDir"
        return
    } catch { Start-Sleep -Seconds 1 }
}
throw "Ollama no respondió. Revisa $logDir\stderr.log"
