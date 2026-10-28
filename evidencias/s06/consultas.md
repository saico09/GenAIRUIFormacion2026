# HDU-027 · Dashboard · 28/10/2026

[Abrir APIs GenAI](http://localhost:3000/d/genai-apis/apis-genai). Se crea desde [dashboard.json](../../observabilidad/dashboard.json), con dos filas y fuente Prometheus. [Provisionado](../../observabilidad/grafana-dashboards.yml): los cambios del archivo se leen cada 30 segundos.

| Fila | A: tráfico, unidad req/s | B: tráfico de errores |
|---|---|---|
| FastAPI | `sum(rate(http_requests_total{service="fastapi"}[5m]))` | `sum(rate(http_requests_total{service="fastapi",status=~"4..\|5.."}[5m]))` |
| Spring Boot | `sum(rate(http_server_requests_seconds_count{service="springboot"}[5m]))` | `sum(rate(http_server_requests_seconds_count{service="springboot",status=~"4..\|5.."}[5m]))` |

Cada panel de errores oculta A/B y muestra la expresión Grafana **`100 * $B / $A`**, con unidad porcentaje (0–100). La barra `|` de la regex significa «o»; en el JSON se guarda sin escape Markdown. La ventana de cálculo es cinco minutos; el dashboard muestra los últimos quince.

Se ejecutaron GET 200 y 404 en ambas APIs y se consultaron los cuatro paneles a través de la API de Grafana, incluida su expresión matemática. Todos devolvieron valores finitos: [resultados y horas](027-comprobaciones.json), [captura](dashboard-027.png). La carga incluye otras peticiones del intervalo, como health y scrapes; no se espera que dos llamadas aisladas produzcan exactamente 50 % en una ventana de cinco minutos. Sin tráfico la división puede no tener un valor definido; no se presenta como 0 %.

Se reinició únicamente Grafana para montar el proveedor y el dashboard. Los datos persistentes de los otros servicios se conservaron. Fuente de configuración: [provisionado oficial](https://grafana.com/docs/grafana/latest/administration/provisioning/) y [expresiones](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/query-transform-data/expression-queries/).
