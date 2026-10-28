# HDU-032 · Logs del LLM · 28/10/2026

Se envió `¿Cuál es el diagnóstico de Ana?` al POST `/chat`, con `patient_id=1` y request_id `hdu032-b1f2ddff60e54e5cb1cb301cf59a9d76`. La respuesta fue 200 y conservó ese header. Loki recibió un evento HTTP y dos eventos LLM con el mismo id: [respuesta, prompts y logs completos](032-llm.json).

| Rama | Modelo | Resultado | Duración de la llamada |
|---|---|---|---:|
| direct | llama3.2:3b | Indicó falta de información y pidió más contexto | 2264,058 ms |
| rag | llama3.2:3b | `Respuesta: Enfermedad Alfa.` y `Fuente: [paciente-1.md/Enfermedad]` | 7735,087 ms |

Ambos eventos tienen status `ok` y sus respuestas coinciden exactamente con el JSON devuelto por la API. La rama directa recibió solo la pregunta; RAG recibió la misma pregunta y los fragmentos Enfermedad y Medicamento de Ana. El modelo y los parámetros se comparten en [llm.py](../../python-api/app/llm.py): temperatura 0, contexto 2048, salida máxima de 256 tokens y timeout de 120 segundos por llamada. El POST completo duró 14458,053 ms; también incluye recuperación y preparación. Son tiempos observados de esta ejecución, no una garantía.

[observability.py](../../python-api/app/observability.py) conserva el id con ContextVar al pasar del middleware al hilo del endpoint. `llamar_llm` registra timestamp UTC, servicio, evento, request_id, rama, modelo, prompt, respuesta, duración y estado. El código también contempla `status=error` y `response=null` cuando falla la llamada; esta comprobación acredita las dos llamadas correctas. Los eventos LLM contienen texto de la pregunta y contexto, por lo que aquí solo se usan datos ficticios.

Consulta comprobada en Explore:

```logql
{service="fastapi"} | json | request_id="hdu032-b1f2ddff60e54e5cb1cb301cf59a9d76" | event="llm"
```

Intervalo: **28/10/2026, 18:05:39.283233–18:07:53.514385 UTC** (**15:05:39–15:07:53 en Santiago**). [032-explore.json](032-explore.json) guarda la URL y las dos líneas visibles. [032-llm.png](032-llm.png) fue inspeccionada: ambas ramas y su request_id están visibles. [capturar_loki.cjs](../../scripts/capturar_loki.cjs) abrió la consulta guardada y comprobó sus ids antes de capturar.

repetir desde `codigo/` (regenera `032-llm.json`):

```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_llm_logs.py
```

La primera comprobación esperaba por error `paciente-001.md` en el verificador; el archivo real y la respuesta de la app eran `paciente-1.md`. Se corrigió esa expectativa y se repitió la prueba completa con resultado correcto. La explicación personal y la revisión de Rui siguen pendientes; no se registran horas ni una sesión realizada.
