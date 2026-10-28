# HDU-029 · Revisión de métricas · 28/10/2026

Se repitió un GET 200 y otro 404 por API después de terminar la carga de HDU-028. Se compararon las métricas antes/después, se esperó a que Prometheus recogiera los valores nuevos y se abrió el dashboard **APIs GenAI** en Edge para comprobar sus paneles. No se modificaron pacientes.

| API y métrica | GET 200 antes → después | GET 404 antes → después |
|---|---|---|
| FastAPI, `http_requests_total` | 23 → 24 | 8 → 9 |
| FastAPI, `http_request_duration_seconds_count` | 23 → 24 | 8 → 9 |
| Spring Boot, `http_server_requests_seconds_count` | 23 → 24 | 8 → 9 |

Las series corresponden a GET `/patients/{id}`. Las cuatro respuestas fueron las esperadas y todos los incrementos fueron exactamente uno. La consulta a Prometheus devolvió 24 y 9 para ambos servicios: [snapshot y peticiones reales](029-peticiones.json).

Los seis paneles se consultaron mediante la API de Grafana usando las consultas del dashboard, incluida la expresión de porcentaje `100 * $B / $A`. Todos devolvieron valores finitos:

| API | Tráfico (req/s) | Error (%) | p95 (segundos) |
|---|---:|---:|---:|
| FastAPI | 0,10473 | 6,66667 | 0,004914 |
| Spring Boot | 0,10473 | 6,66667 | 0,009088 |

Son lecturas de esa comprobación, no objetivos de rendimiento. La ventana de cálculo es de cinco minutos e incluye las demás rutas y los scrapes; el dashboard se refresca cada cinco segundos. Por eso una captura tomada después puede mostrar un porcentaje distinto al de la consulta anterior. Grafana presenta estas latencias pequeñas en milisegundos aunque la consulta las devuelve en segundos.

Evidencia: [valores consultados en Grafana](029-paneles.json), [dashboard exportado](029-dashboard.json), [captura FastAPI](029-fastapi.png) y [captura Spring Boot](029-springboot.png). Se inspeccionaron ambas capturas: las tres gráficas de cada API tienen datos, títulos y unidades legibles.

Tres frases de apoyo para explicarlo:

- **Req/s:** es la tasa de peticiones por segundo, calculada a partir del incremento del contador en los últimos cinco minutos.
- **Error %:** es el porcentaje del tráfico cuya respuesta fue 4xx o 5xx; aquí incluye los 404 provocados a propósito.
- **p95:** estima, a partir de los buckets del histograma, la duración que no supera el 95 % de las peticiones del intervalo; no es el promedio.

El contador acumula peticiones; el histograma acumula cuántas cayeron bajo cada límite de duración. `rate` convierte esos acumulados en tasas, y `histogram_quantile(0.95, ...)` estima el percentil usando los buckets. Si no hay tráfico suficiente, un porcentaje o percentil puede quedar sin un valor definido.

**Revisión de Rui: pendiente.** No se recibió una sesión, comentario ni validación experta durante esta ejecución. Tampoco se atribuye a Marco haber explicado el código o los cálculos. La prueba técnica pasó sin requerir correcciones adicionales; las frases anteriores son material de apoyo. La incorporación a Git la coordina el cierre de HDU-025–029 y no equivale a validación humana.

Para repetir la comprobación HTTP, desde `codigo/`:

```powershell
Get-Content -Raw scripts/verificar_metricas.py | docker compose exec -T python-api python -
Get-Content -Raw scripts/verificar_metricas.py | docker compose exec -T python-api python - --service springboot
```

Para volver a abrir, consultar y capturar los paneles con el verificador del proyecto:

```powershell
$env:NODE_PATH = 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:EVIDENCE_DIR = 'evidencias/s06'
$env:EVIDENCE_PREFIX = 'revision-local'
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts/verificar_dashboard.cjs
```

El verificador lee la clave de Grafana desde `.env` y no la imprime. Usa el endpoint de consulta documentado en la [API de datasources de Grafana](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/data_source/).
