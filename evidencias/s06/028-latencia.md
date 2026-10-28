# HDU-028 · Latencia y carga · 28/10/2026

Se añadieron dos paneles p95, uno por fila, con unidad `s`. Grafana adapta visualmente los valores pequeños a milisegundos.

```promql
histogram_quantile(0.95,sum by(le)(rate(http_request_duration_seconds_bucket{service="fastapi"}[5m])))
histogram_quantile(0.95,sum by(le)(rate(http_server_requests_seconds_bucket{service="springboot"}[5m])))
```

Se ejecutó `scripts/generar_trafico.py`: 20 GET válidos y 5 inexistentes por API, espaciados cada cinco segundos. Las 50 respuestas fueron las esperadas. No se modificaron pacientes.

| API | Inicio de peticiones (America/Santiago) | Última petición | 200 / 404 |
|---|---|---|---|
| FastAPI | 28/10 14:41:27.925 | 14:43:27.935 | 20 / 5 |
| Spring Boot | 28/10 14:41:30.086 | 14:43:29.966 | 20 / 5 |

El proceso completo duró 124,1 s por el tiempo de respuesta final. [Cada petición, estado y hora](028-peticiones.json). Se esperaron más de dos scrapes de 15 s tras la última petición antes de comprobar los paneles; el intervalo aparece dentro de los últimos 15 minutos seleccionados.

Los seis paneles devolvieron valores finitos mediante Grafana, incluidas las expresiones de errores. Últimos p95: FastAPI 0,004760 s y Spring Boot 0,009647 s. [Resultados y hora de comprobación](028-paneles.json), [captura FastAPI](028-fastapi.png), [captura Spring Boot](028-springboot.png). Ambas capturas se inspeccionaron y muestran tráfico, errores y p95.

[Dashboard exportado de Grafana](dashboard.json). Para modificarlo de forma reproducible, edita [su fuente](../../observabilidad/dashboard.json); Grafana la relee cada 30 s. El p95 se estima desde los buckets de duración del servidor; no es el tiempo de red medido por el script.

Para repetir desde `codigo/` en este equipo, usando el Python con el que se ejecutó la prueba (`python` a secas apunta al alias de Microsoft Store):

```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\generar_trafico.py --output evidencias/s06/nueva-carga.json
```

La verificación visual usa `scripts/verificar_dashboard.cjs`, con Playwright/Edge y las variables `EVIDENCE_DIR` y `EVIDENCE_PREFIX` para conservar cada captura. No imprime ni guarda la contraseña de Grafana.
