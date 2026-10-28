# HDU-044 · Arranque, casos básicos y fallos · 28/10/2026

Se siguió el README sobre el entorno existente, sin detener toda la plataforma. El 11/01/2027 sigue siendo la fecha prevista del plan, no la fecha de esta ejecución. [Salida de arranque](044-arranque.txt).

| Caso | Resultado comprobado |
|---|---|
| URLs después del arranque | Los ocho accesos devolvieron HTTP 200: FastAPI `8000/health`, Java `8080/health`, chatbot `8000/`, Grafana `3000/api/health`, Phoenix `6006/`, Argo CD `https://localhost:8443/`, Loki `3100/ready` y Ana de Minikube `8002/patients/1`. [URLs completas y respuestas finales](044-componentes.json) |
| CRUD Python y Java | POST 201, GET/PUT 200, DELETE 204 y GET posterior 404; 28 entradas inválidas por API devolvieron 422. Se conservaron cuatro pacientes Python y tres Java, sin dejar los temporales. [Python](044-crud-python.txt), [Java](044-crud-java.txt) |
| Pregunta de Ana | Dos respuestas visibles: la directa pide contexto; RAG responde Enfermedad Alfa con `[paciente-1.md/Enfermedad]`. Ambas usan `llama3.2:3b`; cuatro nodos, dos llamadas LLM y HTTP 200 comparten el id `9713d51a-b8d1-4cad-88d2-92af8b3e0253`. [Resultados](044-resultados.json), [correlación](044-correlacion.json), [captura inspeccionada](044-caso-1.png) |

## Fallos y repetición

| Caso y pasos | Esperado / obtenido | Corrección y repetición |
|---|---|---|
| Argo CD, HDU-042: sincronizar el primer commit | Se esperaba Succeeded; se obtuvo `counter cannot decrease in value` y duración negativa, aunque los recursos estaban Synced/Healthy | Un Sync real de main, sobre el mismo commit, terminó Succeeded con tiempos coherentes. Se conservó el intento fallido. No acredita una corrección upstream definitiva. [Detalle](../s09/despliegue-inicial.md) |
| Túnel FastAPI, HDU-043: consultar 8002 después de eliminar un pod | Se esperaba GET 200; el túnel ligado al pod eliminado cerró la conexión | El helper comprueba health antes de reutilizar. Abrir un túnel nuevo y reutilizar el sano pasaron; dos pods Ready y Ana 200. La rama Stop-Process no se ejercitó porque el proceso viejo ya había terminado. [Detalle](../s09/gitops.md) |
| Grafana, HDU-044: consultar errores con tráfico positivo y sin series 4xx/5xx | Se esperaba 0 %; ambos paneles quedaban sin puntos porque B no devolvía una serie | B usa la tasa de errores o `0 * tasa_total`. La expresión `100 * $B / $A` devolvió 0 % en ambas APIs; cuando tampoco existe la serie total, conserva No data. [Diagnóstico](044-diagnostico-inicial.json), [repetición](044-validacion-error-cero.json) |
| Túnel Argo CD, HDU-044: repetir Minikube start y abrir 8443 | El helper informaba que estaba activo, pero no se podía establecer la conexión HTTPS | Ahora consulta `/api/version` por HTTPS antes de reutilizar y mientras espera. Abrir un nuevo túnel devolvió 200/v3.5.6; repetirlo conservó el mismo PID sano. [Fallo inicial](044-componentes-inicial.json), [repetición](044-argocd-tunel.json) |

El túnel Argo anterior ya había terminado al probar la corrección: se comprobaron el arranque nuevo y la reutilización sana, sin reiniciar el clúster para provocar otra interrupción. Los pasos funcionales anteriores quedaron correctos. La [guía](../../GUIA.md#comprobar-el-entorno-completo) deja el verificador de los ocho accesos; estos resultados no cubren las ramas de recuperación que no se ejercitaron.

**Seguimiento HDU-046:** el error del contador de Argo CD reapareció al bajar a una réplica. El reintento real terminó Succeeded y GET 200, pero no elimina el riesgo de recurrencia. El [diagnóstico](046-reloj.md) capturó un retroceso simultáneo de unos 3,3 segundos en el nodo y los componentes de Argo mientras Windows avanzaba; no se identificó el origen del ajuste ni una mitigación preventiva soportada. [Estado inicial, repetición y resultado](gitops-preparacion.md). No se modificaron relojes ni servicios.

## Pendiente separado del ensayo

El ciclo completo de detener y arrancar toda la plataforma sigue **NO EJECUTADO** por el rechazo automático anterior registrado en HDU-020. Un `compose up` sobre servicios existentes no acredita ese ciclo. Siguiente acción: volver a evaluar ese ensayo solo cuando pueda realizarse con la autorización necesaria; no se vuelve a intentar detener Qdrant como parte de estas comprobaciones. [Registro original](../S05-arranque.md).

La explicación personal, la demo y la revisión de Rui siguen pendientes. Las pruebas no atribuyen horas ni una sesión realizada.
