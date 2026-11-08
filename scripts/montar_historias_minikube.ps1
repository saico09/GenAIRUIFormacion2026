#Requires -Version 7
param([Alias('Profile')][ValidatePattern('^[a-z0-9][a-z0-9-]*$')][string]$ProfileName = 'genai')
# Mantiene vivo el servidor 9p; comparte solamente datos/historias.
$ErrorActionPreference = 'Stop'
$repoDir = Split-Path -Parent $PSScriptRoot
$minikubePath = Join-Path $repoDir '.local/bin/minikube.exe'
$localDir = Join-Path $repoDir '.local'
$sourceDir = [IO.Path]::GetFullPath((Join-Path $repoDir 'datos/historias'))
$targetDir = '/mnt/genai-historias'
$stateFile = Join-Path $localDir "historias-mount-$ProfileName.json"
$marker = Join-Path $sourceDir '.genai-shared'
$markerText = 'genai-historias-v1'
if (-not (Test-Path -LiteralPath $minikubePath -PathType Leaf)) { throw 'Falta .local/bin/minikube.exe.' }
if (-not (Test-Path -LiteralPath $sourceDir -PathType Container)) { throw 'Falta datos/historias; no se creó una carpeta alternativa.' }
New-Item -ItemType Directory -Path $localDir -Force | Out-Null
$nodeId = (docker inspect --format '{{.Id}}' $ProfileName 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $nodeId -notmatch '^[a-f0-9]{64}$') { throw "No se encontró el nodo Docker del perfil $ProfileName." }
$running = (docker inspect --format '{{.State.Running}}' $ProfileName | Out-String).Trim()
if ($running -ne 'true') { throw 'Reanuda Minikube antes de montar las historias.' }

function Invoke-Node([string]$Command) {
    $result = & $minikubePath --profile=$ProfileName ssh -- $Command 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo comprobar el montaje dentro del nodo Minikube.' }
    return ($result -join "`n").Trim()
}
function Test-OwnedProcess($State) {
    if (-not $State -or $State.source -ne $sourceDir -or $State.profile -ne $ProfileName -or $State.target -ne $targetDir) { return $null }
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($State.pid)" -ErrorAction SilentlyContinue
    if (-not $owner) { return $null }
    if ($owner.ExecutablePath -ne $minikubePath -or $owner.CreationDate.ToUniversalTime().Ticks -ne ([datetime]$State.createdUtc).ToUniversalTime().Ticks -or
        $owner.CommandLine -notlike "*--profile=$ProfileName*" -or $owner.CommandLine -notlike '* mount *' -or
        $owner.CommandLine -notlike "*$sourceDir`:$targetDir*" -or $owner.CommandLine -notlike '*--uid=10001*') {
        # Windows puede reutilizar un PID tras reiniciar. Nunca detener ese nuevo proceso.
        Write-Host 'El PID anterior ya no pertenece al montaje; se conserva ese proceso.'
        return $null
    }
    return $owner
}

$state = if (Test-Path -LiteralPath $stateFile) { Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json -AsHashtable } else { $null }
if ($state -and ($state.source -ne $sourceDir -or $state.profile -ne $ProfileName -or $state.target -ne $targetDir)) {
    throw 'El registro del montaje corresponde a otra carpeta o perfil; no se modificó.'
}
$owner = Test-OwnedProcess $state
$mountIdentity = Invoke-Node ('info=$(timeout 5 findmnt -rn -M {target} -o FSTYPE,SOURCE,OPTIONS); code=$?; if [ "$code" = 0 ]; then printf "%s\n" "$info"; elif [ "$code" = 1 ]; then echo absent; else exit "$code"; fi'.Replace('{target}', $targetDir))
$mounted = $mountIdentity -ne 'absent'
if ($mounted -and ($mountIdentity -notmatch '^9p\s' -or ($state.mountIdentity -and $state.mountIdentity -ne $mountIdentity))) {
    throw 'El montaje del nodo no coincide con el registrado; no se modificó.'
}
$nonce = [guid]::NewGuid().ToString('N')
$probeName = ".mount-probe-$nonce"
$probePath = Join-Path $sourceDir $probeName
$nodeProbePath = Join-Path $sourceDir "$probeName.node"
$nodeProbeTemp = Join-Path $sourceDir "$probeName.tmp"
$reused = $false
try {
    [IO.File]::WriteAllText($probePath, $nonce, [Text.UTF8Encoding]::new($false))
    if ($mounted -and $state -and $state.nodeId -eq $nodeId -and $owner) {
        try { $reused = (Invoke-Node "timeout 5 cat $targetDir/$probeName") -eq $nonce } catch { $reused = $false }
    }
    if (-not $reused) {
        if ($mounted -and (-not $state -or $state.nodeId -ne $nodeId -or -not $state.mountIdentity)) {
            throw 'Ya existe un montaje sin registro propio para este nodo; no se desmontó.'
        }
        if ($owner) {
            Stop-Process -Id $owner.ProcessId -Force
            Get-Process -Id $owner.ProcessId -ErrorAction SilentlyContinue | Wait-Process -Timeout 5
        }
        if ($mounted) { Invoke-Node "sudo umount -f -l $targetDir" | Out-Null }
        # No cambiar permisos de historias: se prepara únicamente el directorio vacío debajo del montaje.
        $empty = Invoke-Node "if test -d $targetDir && test -n `"`$(sudo find $targetDir -mindepth 1 -maxdepth 1 -print -quit)`"; then echo occupied; else echo empty; fi"
        if ($empty -ne 'empty') { throw 'La carpeta del nodo tiene archivos propios; no se ocultaron ni alteraron.' }
        Invoke-Node "sudo install -d -m 0700 -o root -g root $targetDir" | Out-Null
        $process = Start-Process -FilePath $minikubePath -ArgumentList @(
            "--profile=$ProfileName", 'mount', '--uid=10001', '--gid=10001', '--options=cache=none',
            ('"' + $sourceDir + ':' + $targetDir + '"')
        ) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localDir "historias-mount-$ProfileName.out.log") -RedirectStandardError (Join-Path $localDir "historias-mount-$ProfileName.err.log")
        $identity = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)"
        if (-not $identity) { throw 'El proceso del montaje terminó al iniciarse; revisa su log en .local.' }
        $state = @{ pid = $process.Id; createdUtc = $identity.CreationDate.ToUniversalTime().ToString('o'); nodeId = $nodeId; profile = $ProfileName; source = $sourceDir; target = $targetDir }
        $state | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding utf8
        $deadline = (Get-Date).AddSeconds(60)
        $ready = $false
        do {
            $process.Refresh()
            if ($process.HasExited) { throw 'El montaje terminó; revisa .local/historias-mount-*.err.log.' }
            try { $ready = (Invoke-Node "timeout 5 cat $targetDir/$probeName") -eq $nonce } catch { $ready = $false }
            if (-not $ready) { Start-Sleep -Seconds 1 }
        } while (-not $ready -and (Get-Date) -lt $deadline)
        if (-not $ready) { throw 'El montaje no respondió en 60 segundos; no se abrieron accesos a la API.' }
    }
    $state.mountIdentity = Invoke-Node "findmnt -rn -M $targetDir -o FSTYPE,SOURCE,OPTIONS"
    $state | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding utf8
    # Comprobar escritura y reemplazo como el UID/GID de las APIs, sin tocar ningún Markdown.
    $command = "set -e; umask 077; printf old > $targetDir/$probeName.node; printf $nonce > $targetDir/$probeName.tmp; mv -f $targetDir/$probeName.tmp $targetDir/$probeName.node; cat $targetDir/$probeName.node"
    # El nodo no tiene una entrada passwd para 10001; Docker permite usar su UID/GID numérico.
    $writtenLines = docker exec --user 10001:10001 $ProfileName timeout 10 sh -c $command
    if ($LASTEXITCODE -ne 0) { throw 'El usuario de las APIs no pudo escribir/reemplazar en el montaje compartido.' }
    $written = ($writtenLines -join "`n").Trim()
    if ($written -ne $nonce -or [IO.File]::ReadAllText($nodeProbePath) -ne $nonce) { throw 'La escritura UID10001 no coincide con la carpeta local.' }
    if (Test-Path -LiteralPath $marker) {
        if ([IO.File]::ReadAllText($marker).Trim() -ne $markerText) { throw 'El marcador existente no corresponde a esta aplicación.' }
    } else {
        [IO.File]::WriteAllText($marker, $markerText, [Text.UTF8Encoding]::new($false))
    }
    if ((Invoke-Node "timeout 5 cat $targetDir/.genai-shared") -ne $markerText) { throw 'El marcador compartido no es visible desde Minikube.' }
    Write-Host "Historias compartidas con $ProfileName; lectura y escritura UID10001 comprobadas."
    [pscustomobject]@{ Reused = $reused; NodeId = $nodeId; ProcessId = $state.pid; Source = $sourceDir; Target = $targetDir }
} finally {
    foreach ($temporaryPath in @($probePath, $nodeProbePath, $nodeProbeTemp)) {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) { Remove-Item -LiteralPath $temporaryPath -Force }
    }
}
