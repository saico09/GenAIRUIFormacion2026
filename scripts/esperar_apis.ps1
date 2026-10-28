$ErrorActionPreference = 'Stop'
$pendientes = [System.Collections.Generic.List[string]]::new()
$pendientes.Add('http://localhost:8000/health')
$pendientes.Add('http://localhost:8080/health')
$cliente = [System.Net.Http.HttpClient]::new()
$cliente.Timeout = [TimeSpan]::FromSeconds(2)
# Un único límite de 90 s para las dos APIs, incluso si una conexión se atasca.
$limite = [System.Threading.CancellationTokenSource]::new([TimeSpan]::FromSeconds(90))
try {
    while ($pendientes.Count -gt 0) {
        if ($limite.IsCancellationRequested) {
            throw "Las APIs no estuvieron disponibles en 90 s: $($pendientes -join ', ')"
        }
        foreach ($url in @($pendientes)) {
            try {
                $respuesta = $cliente.GetAsync($url, $limite.Token).GetAwaiter().GetResult()
                try {
                    if ([int]$respuesta.StatusCode -eq 200) {
                        $null = $pendientes.Remove($url)
                        Write-Output "OK API disponible: $url"
                    }
                } finally { $respuesta.Dispose() }
            } catch { }
        }
        if ($pendientes.Count -gt 0) {
            # Espera 1 s o termina antes si se agota el límite global.
            $null = $limite.Token.WaitHandle.WaitOne(1000)
        }
    }
} finally {
    $cliente.Dispose()
    $limite.Dispose()
}
