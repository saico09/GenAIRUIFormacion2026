# HDU-037 · Cuatro spans dentro del RAG

Prueba del 28/10/2026 con `¿Qué enfermedad tiene Ana Demo?`, paciente 1 del dataset. [Resultado completo](037-traza.json).

`trace_node` en `app/tracing.py` abre un span por función, guarda su entrada necesaria y la actualización devuelta como JSON, conserva `request_id` y deja que el SDK mida inicio y fin. Los nodos mantienen los eventos `rag_node` existentes. `MODEL_OPTIONS` se comparte entre la petición real a Ollama y los parámetros registrados en el span LLM.

Para repetir desde `codigo/`, con los servicios ya disponibles:

```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_traza.py --prefix hdu037 --output evidencias/s08/037-traza.json
```

En esta máquina se ejecutó el script con el Python disponible en `C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`. Solo usa biblioteca estándar; se pueden cambiar `--prefix` y `--output` para conservar otra ejecución.

| Span | Padre | Duración observada |
|---|---|---:|
| `rag` | Ninguno | 7855.068 ms |
| `retrieval` | `rag` | 3253.391 ms |
| `prompt` | `rag` | 0.334 ms |
| `llamada_llm` | `rag` | 4592.538 ms |
| `respuesta` | `rag` | 0.138 ms |

REST devolvió exactamente cinco spans: una raíz y los cuatro hijos en orden, sin solapamiento entre nodos. Todos tienen estado `OK`, el mismo `request_id`, duración positiva y una única traza. El verificador comprobó JSON de entrada/salida y encadenamiento de valores entre nodos.

`retrieval` devolvió las secciones **Enfermedad** y **Tratamiento** de `paciente-1.md`. Esos mismos textos entraron al nodo `prompt`; su salida completa fue la entrada de `llamada_llm`. El modelo fue `llama3.2:3b`, con `temperature=0`, `num_ctx=2048` y `num_predict=256`. La respuesta real fue `Enfermedad Alfa` con la cita `[paciente-1.md/Enfermedad]`; el nodo `respuesta` la conservó.

También se cotejaron los siete eventos Loki del mismo ID: cuatro nodos, dos llamadas LLM y HTTP 200. Los prompts y respuestas del log coinciden con la traza y la respuesta del endpoint; las ramas directa y RAG conservan modelo y pregunta.

- `request_id`: `hdu037-0977373be58e4c0ba5c7ab734bba2381`
- `trace_id`: `e55201e7c50f71a9938bb739b9a66abd`
- [Abrir ejecución en Phoenix](http://localhost:6006/redirects/traces/e55201e7c50f71a9938bb739b9a66abd)

Se inspeccionaron [la raíz con sus cuatro hijos](037-phoenix.png) y [la entrada/salida del nodo prompt](037-prompt.png). La primera muestra el request_id y los cinco spans; la segunda permite leer los fragmentos de entrada y el prompt completo de salida. [037-phoenix-ui.json](037-phoenix-ui.json) guarda las URLs de la traza y del nodo seleccionado. `scripts/capturar_phoenix.cjs` comprueba los nodos y fragmentos antes de capturar automáticamente ambas vistas.

La UI redondea prompt (0,334 ms) y respuesta (0,138 ms) a 0 ms; los timestamps del SDK en el JSON conservan su duración positiva. No significa que faltaran esos nodos.

Se reconstruyó únicamente `python-api`. La explicación de Marco y revisión de Rui siguen pendientes; no se atribuyen horas reales.
