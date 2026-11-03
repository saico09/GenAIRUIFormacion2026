# Pruebas nuevas · 03/11/2026

Revisé los archivos reales antes de aplicar las sugerencias. El commit de compatibilidad `5733874` sí seguía presente; Python 3.15.2 y PowerShell 7.6.9 están instalados. No deduje el estado a partir de los «resuelto» del informe de Claude.

| Qué probé | Resultado y evidencia |
|---|---|
| Arranque | Los nueve contenedores ya estaban detenidos al empezar. `docker compose up -d --build` y `esperar_apis.ps1` pasaron. [Estado inicial](estado-inicial.json), [componentes HTTP](componentes.json). |
| CRUD Python / Java | 404, 422, crear, consultar, editar y borrar el temporal. Se conservaron los cuatro pacientes Python y los tres Java: [Python](crud-python.txt), [Java](crud-java.txt). |
| Persistencia | Reinicio ordenado PostgreSQL → API; mismas filas y campos: [Python](persistencia-python-api.txt), [Java](persistencia-java-api.txt). |
| Embeddings / Qdrant | Dos ingestas, nueve fragmentos sin duplicados y recuperación por paciente: [ingesta](ingesta-2.json), [búsquedas](recuperacion.json). |
| Chatbot | Las cuatro preguntas desde HTML, fuentes correctas, entrada vacía y controles de espera: [resultados](ui/principal-resultados.json). |
| Error y recuperación | Ollama no disponible: 503 visible y pregunta conservada; tras iniciarlo, el mismo envío pasó: [prueba](ui-error/principal-resultados.json). |
| Métricas / Grafana | Contadores 200/404 de ambas APIs, 50 peticiones y seis paneles con valores: [tráfico](trafico.json), [paneles](grafana/principal-paneles.json). |
| Logs | Cuatro respuestas con el mismo request_id en ambas APIs y correlación en Loki: [HTTP](logs.json), [Loki](loki.json). |
| Grafo / Phoenix | Cuatro nodos ordenados, mismo modelo/pregunta, raíz e hijos con entradas/salidas y siete eventos: [cuatro casos](grafo-logs.json), [traza](traza.json). |
| GitOps | Dos commits reales y push a main; auto-sync a una y después dos réplicas, Synced/Healthy, Succeeded y Ana 200: [una](gitops-una.json), [dos](gitops-dos.json), [repositorio](repositorio.json), [interfaz](argocd/principal-ui.json). |

La escala final comprobada es `3ea28b8d71784e48423a252bb836f661abfc2ee5`. Ambas operaciones pasaron sin el error de duración negativa; esto no identifica ni corrige definitivamente su causa histórica.

Se comprobó un arranque real desde detenido sin ejecutar la parada de Qdrant rechazada anteriormente. La primera consulta de disponibilidad de Loki respondió que aún estaba iniciando; la comprobación posterior pasó. El sondeo preliminar reutilizó por error el estado anterior tras esa respuesta: se corrigió `arranque-http.json` a resultado no válido y se conservó el archivo generado en `arranque-http-original.json`. Para el resultado completo, usa `componentes.json` y las pruebas específicas.

El campo PowerShell de `estado-inicial.json` identifica el host de herramientas 7.6.5. Los helpers se ejecutaron explícitamente con el PowerShell 7.6.9 instalado del usuario. Las capturas de navegador usaron Edge y Playwright del runtime disponible.

La comprensión personal, la demo con Rui y su evaluación siguen pendientes. Estas pruebas técnicas no las reemplazan. Las guías extensas anteriores se conservaron en [documentacion-original](documentacion-original/).

## Al terminar las copias semanales

Se restauraron los nueve servicios principales y Minikube `genai`. FastAPI tuvo un timeout de conexión a PostgreSQL durante el arranque de los pods y el primer túnel falló; se conservó el [error de arranque](fastapi-766cfdc5d5-l5qsj-anterior.txt) y el [error del túnel](restaurar-tunel-primer-error.txt). Una consulta SQL posterior respondió en 20 ms y los dos pods se recuperaron mediante sus reintentos normales, sin cambiar infraestructura ni credenciales. La causa de esa indisponibilidad transitoria no quedó identificada.

La guía ahora espera `rollout status` después de reanudar Minikube y antes de abrir el túnel. Comprobación final: [ocho accesos HTTP 200](estado-final-http.json), [dos pods](estado-final-pods.json), [datos conservados, nueve vectores y dos targets UP](estado-final-datos.json). El chatbot quedó en 8000 y el CRUD de Minikube en 8002.
