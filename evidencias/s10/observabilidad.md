# HDU-045 · Métricas, logs y traza · 28/10/2026

Prueba realizada el 28/10/2026. El 12/01/2027 es la fecha prevista del plan, no la fecha de esta ejecución.

## Carga y dashboard

Se hicieron **50 GET en 124,1 segundos**: 20 respuestas 200 y 5 respuestas 404 por API, sin modificar pacientes. Las peticiones empezaron entre **16:31:52 y 16:33:54 de Santiago**; el JSON conserva hora, estado y duración de cada una. [Peticiones](045-peticiones.json).

| API | req/s | Error % | p95 del servidor |
|---|---:|---:|---:|
| FastAPI | 0,16408 | 10,63830 % | 0,009156 s |
| Spring Boot | 0,16059 | 10,86957 % | 0,022183 s |

Son las últimas muestras numéricas guardadas en [los seis paneles](045-paneles.json). El [dashboard con intervalo fijo](http://localhost:3000/d/genai-apis/apis-genai?from=2026-10-28T19:21:34.439Z&to=2026-10-28T19:36:34.439Z&timezone=browser&refresh=5s) se abrió y comprobó: va de **19:21:34,439 a 19:36:34,439 UTC**, e incluye toda la carga. El verificador usa ese mismo intervalo para consultas y captura, sin depender de «ahora». Las capturas de [FastAPI](045-fastapi.png) y [Spring Boot](045-springboot.png) se volvieron a inspeccionar. El [dashboard exportado](045-dashboard.json) conserva las consultas PromQL y `100 * $B / $A`; el p95 usa `histogram_quantile(0.95, ...)` sobre los buckets.

Estas métricas agrupan la ventana de cinco minutos, incluyendo health y scrapes. Por eso los errores no tienen que marcar 20 % aunque la carga haya hecho 5 de 25 consultas a un id ausente. El p95 es del servidor, no el tiempo de red medido por el script ni la latencia del chat de abajo.

## La misma pregunta en Loki y Phoenix

Pregunta: **¿Qué enfermedad tiene Ana Demo?** Paciente 1, modelo **llama3.2:3b** en ambas ramas, con los mismos parámetros. La rama directa pidió contexto; RAG respondió **Enfermedad Alfa** y citó `[paciente-1.md/Enfermedad]`.

`request_id`: **hdu045-1d77ef312e904ee58d4f481ac8fc1f55**. `trace_id`: **b19855f8ff27eacdf2c0637d4758d59a**.

En [Explore, con el intervalo guardado](http://localhost:3000/explore?panes=%7B%22a%22%3A%7B%22datasource%22%3A%22loki%22%2C%22queries%22%3A%5B%7B%22refId%22%3A%22A%22%2C%22expr%22%3A%22%7Bservice%3D%5C%22fastapi%5C%22%7D+%7C+json+%7C+request_id%3D%5C%22hdu045-1d77ef312e904ee58d4f481ac8fc1f55%5C%22+%7C+event%3D%5C%22llm%5C%22%22%2C%22queryType%22%3A%22range%22%2C%22datasource%22%3A%7B%22uid%22%3A%22loki%22%2C%22type%22%3A%22loki%22%7D%7D%5D%2C%22range%22%3A%7B%22from%22%3A%221793216037646%22%2C%22to%22%3A%221793216055424%22%7D%7D%7D&schemaVersion=1&orgId=1) se comprobaron dos eventos LLM del mismo id, con prompt, respuesta y duration_ms completos: **direct 4735,676 ms**, **rag 5584,526 ms**, ambos `status: ok`. [Eventos](045-loki.json), [consulta y URL exactas](045-explore.json), [captura inspeccionada](045-llm.png).

```logql
{service="fastapi"} | json | request_id="hdu045-1d77ef312e904ee58d4f481ac8fc1f55" | event="llm"
```

La [traza en Phoenix](http://localhost:6006/redirects/traces/b19855f8ff27eacdf2c0637d4758d59a) tiene una raíz `rag` y cuatro hijos en orden, todos OK y con el mismo request_id:

| Nodo | Duración del span |
|---|---:|
| retrieval | 2691,000 ms |
| prompt | 0,375 ms |
| llamada_llm | 5079,909 ms |
| respuesta | 0,184 ms |

Se cotejaron entradas/salidas, orden, duraciones positivas y siete logs: cuatro nodos, dos llamadas LLM y el HTTP. [Comprobación completa](045-traza.json), [captura de la traza](045-phoenix.png), [entrada y salida de prompt](045-prompt.png) y [URLs comprobadas](045-phoenix-ui.json). Los spans miden su propio tramo; la tabla anterior no sustituye duration_ms de los eventos LLM.

Las capturas y los enlaces de Explore/Phoenix se abrieron y se comprobaron. La [guía](../../GUIA.md#repetir-la-observabilidad) deja cómo repetir la carga y generar una consulta nueva. La explicación personal y la revisión de Rui siguen pendientes; no se atribuyen horas ni una demo realizada.
