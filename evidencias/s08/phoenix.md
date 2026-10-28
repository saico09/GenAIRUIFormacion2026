# HDU-036 · Phoenix y correlación · 28/10/2026

Phoenix 20.26.1 está disponible en [localhost:6006](http://localhost:6006), proyecto **genai**, con datos persistentes en `phoenix_data`. La [configuración técnica](036-configuracion.md) recoge imagen/digest, OpenTelemetry 1.45.1, build, pip check y la corrección de los spans automáticos de FastAPI.

La pregunta exacta **¿Qué enfermedad tiene Ana Demo?**, patient_id 1, respondió 200. La rama RAG devolvió `Respuesta: Enfermedad Alfa.` y `Fuente: [paciente-1.md/Enfermedad]`; la directa indicó falta de información. [Petición, respuestas y spans reales](036-traza.json).

| Identificador | Valor comprobado |
|---|---|
| request_id | `hdu036-a91935fe126a42a6b9530146db9ad37e` |
| trace_id | `b257ce77561364693451e5a2324687ed` |
| span | `rag`, tipo CHAIN, estado OK |
| parent_id | null |
| Número de spans | 1; todavía sin spans hijos en esta HDU |

[Abrir la traza local](http://localhost:6006/redirects/traces/b257ce77561364693451e5a2324687ed). Se abrió en Phoenix y se comprobó el request_id en **Attributes** y el trace_id visible. La [captura 036-phoenix.png](036-phoenix.png) fue inspeccionada; [036-phoenix-ui.json](036-phoenix-ui.json) conserva la URL solicitada, la URL resuelta y ambos ids. [capturar_phoenix.cjs](../../scripts/capturar_phoenix.cjs) realizó esa comprobación antes de capturar.

El [resultado de Loki](036-loki.json) contiene los mismos ids de petición en los eventos de ambas llamadas LLM, el HTTP 200 y los nodos del grafo. La consulta usada fue:

```logql
{service="fastapi"} | json | request_id="hdu036-a91935fe126a42a6b9530146db9ad37e"
```

Los logs de nodos no son spans hijos: en esta HDU Phoenix recibe solo la raíz que envuelve `grafo.invoke`. La raíz cubre la rama RAG, mientras el evento HTTP también incluye la llamada directa.

consultar la traza desde PowerShell:
```powershell
Invoke-RestMethod 'http://localhost:6006/v1/projects/genai/spans?trace_id=b257ce77561364693451e5a2324687ed&limit=100'
```

El proveedor OTel sigue siendo global, con BatchSpanProcessor y cierre desde lifespan. El primer ensayo generó spans HTTP automáticos de FastAPI y dejó `rag` como hijo; se corrigió con la opción oficial `telemetry={"tracing": False, "operation_spans": False}`. La repetición final de arriba confirmó una única raíz. El ensayo se conserva como histórico, sin borrar sus trazas.

La explicación personal de Marco y la revisión de Rui siguen pendientes. No se acreditan horas ni una sesión realizada.
