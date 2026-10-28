# HDU-038 · Control y regreso tras el receso

Comprobación técnica realizada el **28/10/2026**, como preparación del control previsto para diciembre. Se ejecutó una pregunta y se guardaron sus métricas, logs y traza. No acredita una revisión con Rui, comprensión personal ni horas de formación realizadas.

## Una misma consulta

- Pregunta exacta: **¿Qué enfermedad tiene Ana Demo?**, patient_id 1.
- request_id: `hdu038-2d68ab54f9fe4c57b8ef54f725df3b6d`.
- trace_id: `24eb89be5309388695f211f0201b04cb`.
- Respuesta RAG: `Respuesta: Enfermedad Alfa.` y `Fuente: [paciente-1.md/Enfermedad]`.
- La respuesta directa indicó falta de información; ambas ramas usaron la misma pregunta y modelo. Los fragmentos recuperados fueron Enfermedad y Tratamiento de Ana.

[038-traza.json](038-traza.json) contiene las respuestas completas, **cinco spans** y **siete logs**: raíz rag, cuatro hijos en orden, cuatro eventos rag_node, dos llamadas LLM y HTTP 200. Todos conservan el request_id y las comprobaciones de entradas/salidas y duración positiva pasaron.

| Evidencia | Resultado y enlaces |
|---|---|
| Métricas del POST | [038-metricas.json](038-metricas.json): `http_requests_total` para POST `/chat`, status 200, pasó de **1 a 2**, incremento exacto de uno; Prometheus recogió el valor 2. |
| Paneles agregados | [Seis valores finitos](038-paneles.json), [dashboard exportado](038-dashboard.json), [captura FastAPI](038-fastapi.png) y [Spring Boot](038-springboot.png). |
| Logs LLM | [Dos llamadas con prompt/respuesta](038-logs.json), [consulta e intervalo de Explore](038-explore.json) y [captura](038-llm.png). Los siete eventos están en `038-traza.json`. |
| Traza | [Abrir Phoenix](http://localhost:6006/redirects/traces/24eb89be5309388695f211f0201b04cb), [captura de los cinco spans](038-phoenix.png), [prompt completo](038-prompt.png) y [URLs de ambas vistas](038-phoenix-ui.json). |
| Disponibilidad | [038-servicios.json](038-servicios.json): nueve comprobaciones GET correctas; APIs, Qdrant con nueve puntos, ambos modelos Ollama, targets Prometheus UP, Grafana, Loki y Phoenix UI/API. |

Las capturas del dashboard, Explore, traza y prompt se inspeccionaron. **Las métricas son agregadas**: request_id identifica la prueba, pero no es una etiqueta de Prometheus. El p95 del dashboard agrupa las rutas y el tráfico de su ventana; no se atribuye a esta consulta. Los tiempos de esta ejecución se consultan en sus spans; la raíz RAG duró 7887,016 ms y no incluye la llamada directa.

Consulta PromQL comprobada:

```promql
sum(http_requests_total{service="fastapi",method="POST",route="/chat",status="200"})
```

Consulta Loki de las dos llamadas, con intervalo **28/10/2026 18:38:27.506237–18:40:53.814409 UTC**:

```logql
{service="fastapi"} | json | request_id="hdu038-2d68ab54f9fe4c57b8ef54f725df3b6d" | event="llm"
```

## Estado del control

Los estados siguientes distinguen lo comprobado técnicamente de los requisitos pendientes; no cierran por sí solos una HDU en Trello.

| Componente o requisito | Estado | Evidencia y pendiente |
|---|---|---|
| Etapa 1 | **Incompleto** | El entorno existente y el chatbot funcionan; [ensayo S05](../S05-ensayo.md), [preflight](../S05-validacion.md) y caso actual. Quedan el ciclo completo desde detenido y la explicación/demo con Rui. |
| Prometheus/Grafana | **Operativo** | Ambos targets UP, contador incrementado y seis paneles finitos; archivos 038 enlazados arriba. La revisión experta sigue pendiente. |
| Loki | **Operativo** | Siete eventos correlacionados y ambas llamadas visibles en Explore, con pregunta, prompt, respuesta e id. |
| LangGraph/Phoenix | **Operativo** | Grafo integrado, raíz y cuatro hijos con entradas/salidas correctas, duración positiva y mismo request_id; capturas inspeccionadas. |
| Ciclo completo desde detenido, HDU-020 | **Bloqueado** | **NO EJECUTADO**: la revisión automática rechazó detener Qdrant. Su recreación automática anterior no acredita ese ciclo. [Pendiente registrado](../S05-pendientes.md). No se repite aquí esa parada. |
| Explicación de Marco y revisión de Rui | **Incompleto** | No se recibieron una explicación personal, demo, comentarios ni valoración experta. El material de apoyo y las pruebas no las sustituyen. |

## Regreso previsto

El **receso 21/12/2026–01/01/2027 queda sin actividad**. No se colocan pendientes en ese período ni se recuperan automáticamente por la noche o en fines de semana. TSTT mantiene su prioridad; no hay nuevas horas desplazadas ni reservas confirmadas que registrar.

La primera acción prevista del **04/01/2027** es seguir [Arrancar en el README](../../README.md#arrancar): Docker Desktop disponible, Compose, espera de las dos APIs, Ollama y health 200 en ambos puertos. Después consultar a Ana y repetir la pregunta RAG con el verificador de trazas, según [la guía de regreso](../../GUIA.md#retomar-después-del-receso). Revisar el resultado y los pendientes antes de continuar HDU-039.

Para usar las vistas: [chatbot](http://localhost:8000), [Targets](http://localhost:9090/targets), [dashboard](http://localhost:3000/d/genai-apis/apis-genai), [Explore](http://localhost:3000/explore) y [Phoenix](http://localhost:6006). Grafana conserva su clave en `.env`; no se incluye aquí.

La revisión prevista con Rui sigue **pendiente**, sin registrar una sesión ni valoración recibida. El cierre de HDU-034–038 incorpora estos archivos a Git; el hash se registra al realizar ese commit.
