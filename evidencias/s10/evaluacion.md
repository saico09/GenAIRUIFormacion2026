# HDU-048 · Comprobación técnica y evaluación pendiente · 28/10/2026

Esta ejecución técnica no acredita una demo con Rui ni una explicación personal de Marco. El **15/01/2027** sigue siendo el cierre objetivo del plan; no se atribuyen una sesión, una hora de preparación ni dos horas trabajadas en esa fecha.

**Estado vigente: dos réplicas FastAPI Ready, Synced/Healthy y GET de Ana 200.** La escala final llegó automáticamente desde Git y terminó Succeeded. Para usar el sistema sigue [el guion](guion.md); para repetir una demo desde una réplica, primero [restablece 2→1 desde Git](gitops-preparacion.md#volver-a-una-réplica-para-otra-demo).

| Parte | Estado y evidencia |
|---|---|
| Preparación técnica | Ocho accesos HTTP 200: APIs, chatbot, Grafana, Phoenix, Argo CD, Loki y FastAPI de Minikube. [URLs y respuestas](048-preparacion.json) |
| Estado inicial | Una réplica Ready, Synced/Healthy, última operación Succeeded y Ana 200 igual a Compose. [Comprobación inicial](048-estado-inicial.json) |
| Modelos y contexto | `llama3.2:3b` y `nomic-embed-text` disponibles; nueve fragmentos en Qdrant. [Comprobación](048-rag-inicial.json) |
| Material de observabilidad | Carga, métricas de ambas APIs, eventos LLM y cuatro nodos RAG preparados y comprobados en [HDU-045](observabilidad.md). Mostrarlos y explicarlos ante Rui sigue pendiente. |
| Cambio GitOps 1→2 | Commit `0e89a564811e6769c40d70281323cb004b1275a7`, auto-sync con `automated: true`, operación Succeeded de **19:49:36 a 19:49:37 UTC**, Synced/Healthy y dos pods Ready. GET de Ana 200, mismo cuerpo que Compose. [Comprobación completa](048-gitops.json), [pods](048-pods.txt) |
| Comprobación visual | La captura inspeccionada muestra Sync OK, revisión 0e89a564 y dos pods. [Captura](048-argocd.png), [estado UI](048-ui.json) |
| Datos conservados | Cuatro pacientes Python, tres Java y nueve puntos Qdrant. [Comprobación de solo lectura](048-datos-conservados.json) |
| Explicación del código y evaluación experta | **Pendientes**. No se ha recibido una valoración de Rui ni se acredita que Marco haya explicado RAG, instrumentación o chart. |

El [guion](guion.md) reúne los comandos y enlaces para la revisión. Los resultados técnicos anteriores siguen disponibles como evidencia; no sustituyen la explicación ni una valoración humana.

La primera captura agotó los 30 segundos de espera del navegador. Repetir el mismo script y la misma revisión pasó, sin cambiar servidor, chart ni operación de Argo CD; no se atribuyó una causa al timeout. [Registro del reintento UI](048-ui-reintento.json). La escala automática correcta de esta ejecución no acredita que el error recurrente del contador de Argo esté corregido definitivamente.

## Pendientes y siguiente acción

| Pendiente | Siguiente acción concreta |
|---|---|
| Explicación personal de Marco | Recorrer el guion y explicar el flujo RAG, las métricas/logs/trazas y el chart con sus propias palabras. |
| Demo y valoración de Rui | Coordinar la revisión dentro de jornada y según prioridad TSTT; registrar fecha real, observaciones y resultado cuando ocurra. No hay una sesión confirmada aquí. |
| Correcciones de la revisión | Todavía no se han recibido. Cuando existan, anotar cada corrección, repetir el caso y enlazar su evidencia. |
| Error recurrente de Argo CD | Conservar cualquier recurrencia y su reintento real. El [diagnóstico](046-reloj.md) observó un salto del reloj Linux compartido, pero no identificó qué lo ajusta ni una mitigación preventiva soportada. |
| Arranque completo desde detenido | Sigue **NO EJECUTADO** por el rechazo automático previo de HDU-020. Revisar cómo realizar ese ensayo con la autorización necesaria; los arranques sobre servicios existentes no lo acreditan. [Registro](../S05-arranque.md) |

Se mantiene el receso **21/12/2026–01/01/2027 sin tareas ni recuperación automática**. No se registran horas personales, reuniones o aprobaciones inventadas. Solo corresponde marcar Finalizado lo que reúna sus criterios y validación; las revisiones pendientes quedan explícitas.
