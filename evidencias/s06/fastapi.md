# HDU-025 · 28/10/2026

FastAPI expone `GET /metrics` con prometheus-client 0.26.0. `http_requests_total` cuenta peticiones por método, ruta y status; `http_request_duration_seconds` agrupa su duración en segundos mediante buckets.

Se reconstruyó solo Python y se esperó su disponibilidad. La prueba ejecutó GET `/patients/1` → 200 y `/patients/999999` → 404. Comparó antes/después: el contador y el count del histograma aumentaron exactamente uno para cada status, ambos con `route="/patients/{id}"`. Ninguna serie contiene los ids concretos. Código de salida 0, sin modificar pacientes.

Salida real: [fastapi-metricas.txt](fastapi-metricas.txt). Código: [metrics.py](../../python-api/app/metrics.py). Para repetir desde `codigo/`:

```powershell
Get-Content -Raw scripts/verificar_metricas.py | docker compose exec -T python-api python -
```

Las duraciones miden el procesamiento hasta construir la respuesta; estas APIs no sirven respuestas en streaming. Las métricas incluyen sus rutas HTTP, también las consultas a `/metrics`. Las etiquetas usan la plantilla de ruta; las rutas no reconocidas comparten `unmatched` para no generar una serie por URL arbitraria.

Dependencia estable comprobada: [PyPI 0.26.0](https://pypi.org/project/prometheus-client/0.26.0/); uso del histograma según [documentación oficial](https://prometheus.github.io/client_python/instrumenting/histogram/).
