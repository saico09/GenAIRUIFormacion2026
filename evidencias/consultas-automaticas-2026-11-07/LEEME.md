# Consultas que se guardan y RAG útil

Se trabajó sobre el Compose principal que Marco había levantado. Sólo se reconstruyeron las APIs; PostgreSQL, Qdrant y SonarQube conservaron sus contenedores y volúmenes.

El problema tenía dos causas: el prompt anterior sólo permitía extraer hechos ya escritos y `/chat` no guardaba conversaciones. Los tres relatos nuevos de Ana llegaban correctamente, pero terminaban en «No hay información suficiente» y no cambiaban el informe.

Ahora el chat compara y guarda: texto del usuario, ambas respuestas, modelo y UUID. Java escribe el diario en el Markdown y una copia completa en `java.medical_consultations`. La tabla de enfermedad/tratamiento/medicamento mantiene su confirmación aparte. El índice incluye los hechos confirmados y el texto relatado, identificado como tal; **nunca vuelve a ingerir respuestas de IA como hechos**.

`public.transaction_logs` registra cada operación API Python/Java, con UUID de ejecución, request_id, verbo, ruta, código HTTP y cuerpos. El mismo UUID enlaza la llamada Python con la escritura Java. Los cuerpos se conservan como texto, incluso para errores y Markdown; hasta 128 KiB por cuerpo, con flags de recorte. Se excluyen sondas, métricas, assets y documentación. No se copian headers ni variables de entorno. Si falla el INSERT del log, queda un evento de error; no se afirma que una operación de negocio ya realizada se revirtió.

Para usarlo: abre la página, elige Ana y pulsa **Comparar y guardar**. Después, **Abrir informe del paciente**. Debajo de los registros confirmados aparecen sus consultas; el archivo descargado y PostgreSQL contienen el mismo diario. Una repetición con el mismo `X-Execution-ID` recupera la respuesta original; cambiar el texto con ese UUID devuelve 409.

Pruebas y archivos:

| Comprobación | Evidencia |
|---|---|
| Tres consultas originales de Ana, guardado único, reintento, MD=SQL y ambas APIs correlacionadas | [ana-consultas.json](ana-consultas.json) |
| Qwen y Llama con el mismo prompt, fuentes y opciones | [modelos-ab-v2.json](modelos-ab-v2.json), [salidas y validación posterior](modelos-ab-final.json) |
| Navegador real: consulta, informe, recarga, descarga, alta/edición confirmada y limpieza del temporal | [ui-real/resultados.json](ui-real/resultados.json) |
| Formato, citas, separación del diario, fallo de embeddings y reutilización de vectores | [contratos-offline.txt](contratos-offline.txt) |
| Java: SQL/MD, idempotencia, restauración de archivo ausente, edición A→B→A, límites, 404/405/422 | [java-consultas-final.json](../consultas-persistentes-2026-11-07/java-consultas-final.json) |
| Auditoría Python real: 14 peticiones cotejadas con sus filas SQL | [auditoria-python-real.json](../consultas-persistentes-2026-11-07/auditoria-python-real.json) |
| Auditoría Python y arranque, sin red ni DB | [auditoria-python.json](../consultas-persistentes-2026-11-07/auditoria-python.json) |
| Cuatro consultas, dos propuestas reales, reintentos, diario, SQL y limpieza del temporal | [regresion-temporal.json](regresion-temporal.json) |
| Quinta consulta temporal: cinco spans Phoenix y siete eventos Loki | [regresion-traza.json](regresion-traza.json) |
| Eliminar citas de preguntas que no describían síntomas: replay de salida real, sin nueva inferencia | [relevancia-consulta-replay.json](relevancia-consulta-replay.json) |
| Nueve accesos HTTP 200 y ambos targets UP | [servicios.json](servicios.json) |

La comparación de ocho casos obtuvo 8/8 con Qwen y 5/8 con Llama antes de las comprobaciones adicionales. La revalidación de esas salidas reales con el validador final queda en 8/8 y 6/8, respectivamente; no se volvió a inferir para ese cálculo. Se eligió `qwen3:4b-instruct-2507-q4_K_M`, disponible en la [biblioteca de Ollama](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M). Es una muestra funcional local, no una certificación clínica. La [ficha oficial de Qwen](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) describe esta variante como Instruct sin modo de razonamiento. Ambas ramas conservan el mismo modelo, pregunta, temperatura 0, contexto 4096 y salida máxima 1024 tokens. [Ollama documenta el uso de esquemas JSON](https://docs.ollama.com/capabilities/structured-outputs).

Una prueba posterior encontró una cita literal de tratamiento usada como respuesta sobre cirugía. Se conserva el [fallo](regresion-temporal-fallo-cirugia.json); se añadió una comprobación del tipo de dato solicitado para cirugía, alergias, dosis y nacimiento. También se conserva el [fallo de recuperación](regresion-temporal-fallo-recuperacion.json): al pedir consultas anteriores ahora se buscan hasta tres notas. Al preguntar por síntomas se descartan citas de simples preguntas documentales. Las citas se validan contra las fuentes; esa comprobación no es un evaluador semántico general. La orientación sigue siendo texto generado y revisable.

Para repetir pruebas con un paciente temporal:

```powershell
python -X utf8 scripts/verificar_consultas_regresion.py
python -X utf8 scripts/verificar_auditoria_python.py
```

Para repetir las tres consultas de Ana con sus UUID originales, sin duplicarlas:

```powershell
python -X utf8 scripts/verificar_consultas_integradas.py
```

Los ensayos CRUD eliminan sólo sus pacientes temporales. Sus transacciones y respaldos permanecen en SQL por diseño. Las consultas de Ana quedan en su informe local; los diagnósticos previos se conservan. El corpus inicial de tres informes/nueve fragmentos describe la semilla, no el conteo después de usar el chat.

El Markdown admite 1 MiB y 50 registros confirmados. Un archivo ausente se puede reconstruir desde su último respaldo SQL. No se sobreescribe silenciosamente un archivo conflictivo. Archivo y SQL tienen compensación ante errores normales, pero no una transacción distribuida resistente a cualquier cierre forzado entre ambas escrituras. Un conflicto se registra por paciente y no impide arrancar al resto de la API. Los respaldos usan un orden de escritura estable, independiente de saltos del reloj.

Esta es una ampliación solicitada por Marco. No cambia las 48 HDU, las 80 horas previstas, el calendario ni acredita revisiones de Rui. GitOps conserva el microservicio CRUD existente.
