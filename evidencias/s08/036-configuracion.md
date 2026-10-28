# HDU-036 · Primera traza RAG

Prueba técnica del 28/10/2026. Phoenix está en `http://localhost:6006`, con imagen oficial `arizephoenix/phoenix:version-20.26.1` fijada al digest `sha256:623813cbf1bbd4811456bb4936f21666ae50a1fbf862cf59ea0e3ca824b6b114`. El volumen `phoenix_data` guarda sus datos en `/data`; el puerto solo está publicado en localhost.

Python 3.15.2 usa `opentelemetry-sdk` y `opentelemetry-exporter-otlp-proto-http` 1.45.1. Se comprobaron build, imports y `pip check`: [versiones](036-runtime.json), [pip check](036-pip-check.txt). Phoenix se ejecuta en su contenedor; no se instalaron los paquetes Phoenix/OpenInference que excluyen Python 3.15.

`app/tracing.py` configura el proyecto `genai`, `service.name=python-api` y el exportador HTTP `http://phoenix:6006/v1/traces`. Usa `BatchSpanProcessor`: la petición no espera un envío de telemetría. El exportador tiene timeout de cinco segundos y el lifespan cierra el proveedor al apagar la API. Se conserva un proveedor OTel global.

`POST /chat` abre un span `rag` de tipo `CHAIN` alrededor de `grafo.invoke`, con el mismo `request_id` de la petición. Esta HDU todavía no agrega spans hijos a los nodos.

El primer ensayo detectó que FastAPI 0.162 activa spans HTTP y de operaciones cuando existe un proveedor global. `rag` quedó hijo de `fastapi.endpoint`; esa prueba no cumplía el criterio de raíz. Se corrigió mediante la opción oficial `FastAPI(telemetry={"tracing": False, "operation_spans": False})`, confirmada en `fastapi/applications.py` y `fastapi/telemetry/_api.py` de la dependencia instalada. El ensayo queda en [036-ensayo-autotelemetria.json](036-ensayo-autotelemetria.json); sus trazas históricas no se borraron.

La repetición final usó exactamente `¿Qué enfermedad tiene Ana Demo?`, del dataset, paciente 1. Respondió `Enfermedad Alfa` con `[paciente-1.md/Enfermedad]`. La consulta REST por ID y por traza devolvió **un solo span `rag`, `parent_id=null`, estado `OK` y duración positiva**, sin spans HTTP en esa ejecución. [Estado y comprobaciones](036-traza.json).

- `request_id`: `hdu036-a91935fe126a42a6b9530146db9ad37e`
- `trace_id`: `b257ce77561364693451e5a2324687ed`
- [Abrir la traza local](http://localhost:6006/redirects/traces/b257ce77561364693451e5a2324687ed)

Comandos usados para levantar solo lo afectado:

```powershell
docker compose config --quiet
docker compose up -d --no-deps phoenix
docker compose up -d --build --no-deps python-api
docker compose exec -T python-api pip check
```

Consulta de la traza, después de que termine la exportación por lotes:

```powershell
Invoke-RestMethod 'http://localhost:6006/v1/projects/genai/spans?trace_id=b257ce77561364693451e5a2324687ed&limit=100'
```

La comprobación visual y correlación con Loki se documentan por separado en `phoenix.md`. La explicación de Marco y revisión de Rui siguen pendientes; esto no acredita horas reales.

Fuentes de versiones: [SDK OpenTelemetry](https://pypi.org/project/opentelemetry-sdk/1.45.1/), [exportador HTTP](https://pypi.org/project/opentelemetry-exporter-otlp-proto-http/1.45.1/), [release Phoenix](https://github.com/Arize-ai/phoenix/releases/tag/arize-phoenix-v20.26.1).
