# Historias clínicas y RAG · 07/11/2026

Para usarlo: abre [la página](http://localhost:8000), entra en **Pacientes** y pulsa un nombre. **Nueva consulta → Preparar con IA → revisar → confirmar** añade un registro. También puedes escribirlo manualmente. La tabla muestra su UUID, enfermedad, tratamiento y medicamento; debajo puedes descargar o editar el Markdown, con confirmación.

Cada informe se llama `paciente-ID-nombre.md`, pertenece al paciente Java y conserva los UUID al editar o renombrar. Java guarda el archivo; Python actualiza su índice. Si falla Qdrant, el archivo confirmado se conserva y puedes reintentar. Una pregunta o respuesta del chatbot no se guarda como dato clínico.

## Qué cambió

- Tres historias sintéticas más completas, con contexto de consulta y seguimiento; siguen siendo datos inventados. Tres fragmentos por registro, con búsqueda limitada a tres resultados del paciente seleccionado.
- El mismo modelo y pregunta en ambas ramas, con `temperature=0`, contexto 4096 y máximo 1024 tokens. RAG recibe además las fuentes y reglas de lectura.
- RAG pide una salida estructurada y comprueba cada cita literal contra el fragmento indicado. Las reglas conservadoras de esta demo restringen las preguntas a hechos registrados; ante datos faltantes, fuentes inválidas o solicitudes de consejo devuelve `No hay información suficiente`.
- La IA prepara valores para revisar. La evidencia se copia directamente de una oración afirmativa de la nota que contenga el valor y su campo; no la redacta el modelo. Sólo la confirmación crea el registro y su UUID.
- No se agregó una tabla SQL de consultas ni memoria conversacional. Esta ampliación fue solicitada por Marco sobre el stack del plan de Rui; no acredita nuevas horas, reuniones ni revisión experta.

## Comprobaciones

| Ensayo | Evidencia |
|---|---|
| Java: confirmación, revisión 409, validación 422, UUID, concurrencia, límites, descarga, renombrado y borrado | [9 bloques correctos](../historias-clinicas-2026-11-07/historias-java.json) |
| Primera carga con PostgreSQL/Java nuevos: informes conservados, IDs 1–3, concurrencia, rollback y secuencia | [10 comprobaciones correctas](bootstrap-java.json) · [uso y reproducción](bootstrap-java.md) |
| Java → Markdown → Qdrant: 3 → 3 → 6 → 3 → 0 puntos, aislamiento y fallo de transporte controlado | [Integración correcta y datos previos conservados](../historias-clinicas-2026-11-07/clinica-integracion-final.json) |
| RAG: hechos de los tres pacientes, tres datos juntos, fechas, dosis ausente, síntomas, otro paciente y fecha de nacimiento fuera del corpus | [15/15 casos reales](rag-clinico-final.json) |
| Las cuatro formulaciones breves de síntomas del experimento original | [4/4 abstenciones correctas](rag-sintomas-originales.json) |
| Propuesta de tres hechos explícitos y pregunta de síntomas, con modelo real y sin escrituras | [Ambos casos correctos](clinica-propuestas-reales.json) |
| Portal: CRUD, exploradores, 200/404/422, cancelación y cuatro vistas móviles | [12 comprobaciones](portal-regresion/portal-resultados.json) |
| Historia en navegador con APIs y Qdrant reales, pero propuesta/chat simulados | [Integración de interfaz](ui-integracion/resultados.json) |
| Nota → IA real → revisar/cancelar/confirmar → UUID/Markdown → edición → RAG real → renombrar/eliminar, sin simulaciones | [Recorrido completo correcto](ui-llm-real-final/resultados.json) · [detalle y capturas](interfaz.md) |
| Ambos CRUD y preservación de las filas | [Resultados](../historias-clinicas-2026-11-07/crud-resultados.json) |
| Métricas, Loki, logs y dos targets activos | [Observabilidad sin generación](../historias-clinicas-2026-11-07/observabilidad-sin-llm.json) |
| LangGraph/Phoenix y Loki: raíz + cuatro nodos, dos llamadas LLM, siete logs, salida original y validada correlacionadas | [Traza real correcta](traza-llm-final.json) |
| Reanudación de Minikube, SQL, dos réplicas y Argo saludable; perfil devuelto a detenido | [Comprobación del despliegue CRUD existente](../historias-clinicas-2026-11-07/minikube-smoke.json) |

Los ensayos de RAG cotejan datos y fuentes y se revisaron sus respuestas. No demuestran calidad clínica general ni comprensión de cualquier formulación: el modelo local puede equivocarse al interpretar una pregunta. La extracción también exige revisión humana antes de guardar.

## Fallos encontrados y corregidos durante las pruebas

Los resultados intermedios se conservaron. El prompt por sí solo no evitó citas omitidas o inventadas; la primera salida JSON tampoco aseguró relevancia para preguntas de síntomas. Por eso se añadieron validación literal, abstención completa y reglas explícitas de alcance. Los límites son parte del resultado, no una garantía universal.

La ingesta también normalizaba CRLF a LF y calculaba una revisión distinta de Java. Se corrigió leyendo los bytes de texto sin normalizar saltos: [ingesta corregida](ingesta-crlf.json). La primera comparación que detectó el cambio está conservada, y la integración final verifica payloads y vectores íntegros.

La primera prueba de propuestas extrajo los valores, pero el modelo inventó sus frases de evidencia. La validación las rechazó sin guardar nada: [ensayo inicial](ui-llm-real/resultados.json). La implementación posterior obtiene esa evidencia directamente de la nota.

El A/B previo con TOP2 y el corpus anterior sigue en [su informe histórico](../revision-rag-2026-11-07/LEEME.md); no se mezcla con estas pruebas.

## Para repetir

Desde `codigo/`, con los servicios iniciados:

```powershell
docker compose up -d --build --no-deps python-api java-api
python -X utf8 -B java-api/src/test/python/verificar_historias.py --base-url http://127.0.0.1:8080 --history-dir datos/historias --output evidencias/mi-prueba-java.json
python -X utf8 -B scripts/verificar_clinica.py --proposals --check-qdrant-error --output evidencias/mi-prueba-clinica.json
python -X utf8 -B scripts/verificar_rag_clinico.py --output evidencias/mi-prueba-rag.json
```

Ejecuta las pruebas una por vez. Las dos primeras usan pacientes temporales propios y los retiran; el ensayo RAG consulta el corpus ficticio inicial. Los resultados semanales se guardan en `ejecuciones/` de cada copia y su arranque continúa en `LEVANTAR.txt`.
