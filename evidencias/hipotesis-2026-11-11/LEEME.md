# Hipótesis útiles, sin repetir preguntas · 11/11/2026

**Cierre técnico completado, con límites de precisión documentados.** Ambas ramas usan lo ya relatado para dar una hipótesis provisional, alternativas condicionales y límites, sin cuestionarios. RAG separa los antecedentes citados de la orientación. Las respuestas no confirman enfermedades automáticamente.

Fuente de la aplicación: `1b614d3e269ac42542ad7f5ff817355d9defa4b9`. Publicación y notas Trello se registran por separado en el contexto de la carpeta de formación. Es una ampliación personal de Marco: no añade diagnóstico diferencial al plan original de Rui, HDU, horas, fechas ni validaciones humanas.

## Por qué fallaba

El prompt anterior pedía **una a tres preguntas** y repetía datos sobre alimentos y postura ya aportados. No había un bucle en el programa. [Reproducción anterior](antes.json).

También se reprodujo otro fallo por HTTP: tras guardar un relato, el siguiente recuperaba aquella nota semejante. El modelo elegía `record_lookup`, citaba la consulta anterior y dejaba vacía la orientación. El helper confundía la nota con una petición documental por «síntomas» e «indica»; el validador la descartaba. Se conservan el [HTTP fallido](persistencia-gemma4.json) y su [RAW de Loki](persistencia-relato2-loki.json).

El ajuste reconoce construcciones claras de relato actual y limita su esquema a orientación no vacía. Las solicitudes documentales explícitas/mixtas y las guardas de citas se mantienen. Se corrigió además la confusión de «consumo constante» con «consta». La regla es acotada, no un clasificador semántico universal: «tengo un PDF» también coincide con una construcción actual; el modelo debe evitar inventarle un problema médico. La repetición HTTP corrigió los dos relatos ensayados, incluido el segundo con una nota previa semejante.

Qwen3, Qwen3.5 y Llama conservaron fallos semánticos en las variantes probadas. Las [revisiones](revision-v4-v5-llama.json), [4B](revision-qwen35-v5.json) y [9B](revision-qwen35-9b-v5.json) no se ocultan ni se convierten en un ranking: cambiaron reglas heurísticas entre ensayos. El [sondeo](transporte-qwen35-9b.json) verificó transmisión de `system` por generate/chat; las entradas cortas medidas cabían en 4.096 tokens. No explicaban los fallos de esos casos. Agotar la salida con `done_reason=length` fue un problema distinto.

## Configuración usada

Misma pregunta, `gemma4:12b` y opciones en ambas ramas:

```json
{"temperature":1,"num_ctx":8192,"num_predict":1024,"top_p":0.95,"top_k":64,"draft_num_predict":0}
```

Se usa `/api/generate`, `think=false`, `stream=false`, `keep_alive="1m"` y límite de 180 segundos por llamada. El muestreo sigue la [configuración oficial de Gemma 4](https://ollama.com/library/gemma4:12b); contexto y salida son decisiones de la app. [Ollama Thinking](https://docs.ollama.com/capabilities/thinking) documenta el control y la separación del razonamiento.

Un arranque de Gemma falló al inicializar CUDA, con salida `0xc0000409`; se conserva el [error](gemma4-regresion-completa-cancelacion.json). Desactivar la generación especulativa permitió completar la batería posterior iniciada en frío. No se diagnosticó falta de memoria ni se probaron catorce arranques fríos independientes.

El log conserva tokens, `done_reason`, opciones y booleanos de solicitud/presencia de `thinking`; **nunca su contenido**. Se rechazan respuestas vacías, incompletas o truncadas. [Campos oficiales de la API](https://docs.ollama.com/api/generate).

## Pruebas y alcance

| Comprobación | Resultado |
|---|---|
| [Contratos finales](offline-enrutamiento-final.json) | **75 PASS**: 32 contratos, 33 de arranque/auditoría/LLM y 10 del corpus. El [intento previo fallido](offline-enrutamiento.json) se conserva. |
| [Replay del RAW](replay-enrutamiento.json) | **7/7**, sin inferencia nueva. El esquema excluye el modo incorrecto; el RAW antiguo sigue rechazándose, sin transformarlo en un acierto. |
| [Batería previa al ajuste de intención](gemma4-regresion-sin-draft.json) | **14 respuestas completas y 13/14 heurísticas** desde un arranque frío, sin 500 ni truncamiento. La [revisión manual](revision-gemma4-regresion-sin-draft.json) conserva sus límites. No se reetiqueta como reejecutada. |
| [Corpus real previo al ajuste](corpus-gemma4-real.json) | **14/14**, con Ollama/Qdrant. Historias/consultas y 15 puntos intactos; sin `/chat` ni sincronización. Los GET Java generan auditoría normal. |
| [Repetición HTTP final](persistencia-gemma4-enrutamiento.json) | **4/4 respuestas y ocho controles** de guardado exacto, MD/SQL, reintento, separación de registros e índice. Comparaciones de unos **184 y 164 segundos**. Temporal 53 retirado. |
| [Regresión integral](regresion-http-enrutamiento/resultados.json) | **Cuatro casos, siete bloques y dos propuestas correctos**; idempotencia/409, SQL/MD y auditoría. Una quinta consulta verificó [cinco spans Phoenix y siete eventos Loki](regresion-http-enrutamiento/regresion-traza.json). Temporal 54 retirado. |
| [Navegador real](ui-real-02/resultados.json) | **Cuatro bloques correctos**, sin mocks; escritorio/móvil revisados. El [primer intento](ui-real-01/resultados.json) falló por un selector antiguo del verificador, corregido sin cambiar la app. Temporales 55/56 retirados. |
| [Copias y Drive](entregas.json) | S4–S10 sobre `1b614d3`: **280 contratos offline y siete revisiones estáticas**. S4/S8: **dos coordinadores y cuatro respuestas reales**, con recuperación sintética fija; sin llamar a `/chat` ni probar SQL, persistencia, Qdrant, Compose o GitOps semanales. S4 de Drive reemplazada y releída con el mismo ID. |
| [Cierre del entorno](cierre-entorno-final.json) | **8/8**: once contenedores, sólo Python recreado; cinco pacientes/Markdown intactos, SQL alineado, nueve HTTP 200, dos targets UP y código servido igual a la fuente. Los 15 puntos Qdrant conservan IDs, payloads y vectores. Copias y Minikube detenidos. |

Los respaldos y la auditoría de los temporales se conservan como exige la app. Los pacientes e informes originales permanecen iguales.

**Límites visibles:** la [revisión HTTP](revision-persistencia-enrutamiento.json) conserva «hernia hiatal complazada» en una alternativa condicional; no se retoca ni se considera terminología validada. La [revisión UI](ui-revision-manual.json) registra alternativas poco precisas. En S4 se reutiliza condicionalmente un síntoma negado; en S8 una supuesta alternativa es otro síntoma, no un diagnóstico distinto. Los chequeos funcionales no detectan toda imprecisión: **no se acredita exactitud clínica general**.

La [evidencia pública de las entregas](entregas.json) conserva el resumen semanal, revisión S4/S8, comprobación Drive y hashes de los originales locales. Estos siguen en `dailys/HIPOTESIS_VERIFICADAS_2026-11-11.json`, `dailys/HIPOTESIS_COORDINADORES_REVISION_2026-11-11.json` y `dailys/_herramientas/drive-hipotesis-s4-verificado-2026-11-11.json`. El ajuste final del verificador sólo recibió sintaxis/estática; no se repitieron los 280 contratos. No se releyeron remotamente los otros nueve documentos ni se volvieron a ejecutar las diez pilas completas.

## Entorno recuperado

[WSL estaba bloqueado](entorno-inicial.json). Con autorización expresa de Marco se recuperó su servicio tras verificar y terminar sólo `wslservice.exe`. [Reporte sanitizado](recuperacion-wsl.json). Una segunda interrupción coincidió con una [instalación externa de WSL 3.0.5.0](actualizacion-wsl-externa.json), no iniciada por esta tarea; no se atribuye al modelo ni a OOM.

Después se comprobaron errores 1920 en dos sockets Docker. Con los procesos verificados detenidos, su directorio se renombró a `run-stale-20261111`, conservándolo y sin tocar volúmenes. La [recuperación anterior al build](recuperacion-docker-final.json) conservó once IDs y los datos; después se recreó sólo Python.

El [primer cierre](cierre-entorno.json) incluyó un runner efímero que heredaba etiquetas Compose y encontró un 503 transitorio de Loki. El runner terminó; Loki volvió a 200 sin reinicio, con el mismo ID y contador de reinicios cero. La repetición pasó 8/8. Se conserva el fallo sin atribuir una causa interna no comprobada a Loki.

## Para repetir

Desde `python-api`, los ocho contratos del transporte: `python -m unittest discover -s tests -p test_llm.py -v`.

Desde `codigo`, las 14 inferencias —usa un archivo de salida nuevo—:

```powershell
python -B scripts/verificar_hipotesis.py --phase inference --stop-on-http-error --output evidencias/hipotesis-2026-11-11/mi-repeticion.json
```
