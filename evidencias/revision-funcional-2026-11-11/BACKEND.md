# Revisión real del backend · 11/11/2026

Las funciones siguen disponibles en el entorno principal. Pasaron **29 peticiones HTTP y 21 comprobaciones** con un único paciente temporal (57), ya eliminado. No se modificó la aplicación para conseguir este resultado.

| Comprobación | Resultado |
|---|---|
| Pacientes | Python y Java muestran los mismos cinco pacientes: 1, 2, 3, 4 y 24. Crear por Python, actualizar por ambas APIs y borrar por Java funcionó. |
| Enfermedad, tratamiento y medicamento | Alta, lectura, edición y borrado cruzados entre Python y Java; el UUID y los tres campos coinciden en SQL y Markdown. |
| Informe automático | El alta creó el MD y su respaldo SQL. Renombrar cambió el nombre representativo conservando la asociación. |
| Edición del informe | Descarga y edición confirmada por Java; el cambio también apareció en la tabla de registros y en Python. |
| Auditoría | Las 27 operaciones del temporal produjeron 27 filas, con 27 UUID distintos y `patient_id=57`. Los dos listados generales completan las 29 peticiones. |
| Conservación | Todos los registros SQL previos, los cinco pacientes y los cinco archivos originales conservaron sus hashes. Ningún contenedor se reinició ni recreó. |

Las cuatro tablas actuales están en el esquema **`public`**:

- `patients`: identidad, nombre, nacimiento y correo del paciente.
- `patient_diseases`: UUID del registro, paciente, enfermedad, tratamiento y medicamento; refleja los registros confirmados del MD.
- `medical_consultations`: consultas y versiones completas del MD. Había 169 filas; la prueba añadió once respaldos propios, conservados al eliminar el temporal.
- `transaction_logs`: un solo campo UUID, `id`, por operación; también tiene `patient_id`, servicio, verbo, operación, código HTTP y cuerpos. Había 1178 filas; las 29 peticiones añadieron 29, sin cambiar las anteriores.

Las rutas de pacientes y enfermedades son iguales en ambas APIs (`localhost:8000` y `localhost:8080`): `/patients`, `/patients/{id}`, `/patients/{id}/diseases` y `/patients/{id}/diseases/{uuid}`. Java también sirve `/patients/{id}/history` y `/patients/{id}/history.md` para consultar/editar y descargar el informe.

El [inventario](backend-inventario.json) comprueba que los 33 archivos Python servidos coinciden con la carpeta local en el corte `a5228c4`. El JAR Java queda identificado por hash y probado por sus contratos HTTP; no se recompiló para afirmar igualdad binaria con las fuentes. [Recorrido y conservación](backend-crud-cruzado.json).

También pasaron [22 contratos offline de unificación](backend-unificacion-offline.json): formato, validación, compensación de archivos y asociación del paciente en la auditoría. La red estaba bloqueada y sólo se usaron archivos temporales y sesiones simuladas.

Este ensayo no llama al LLM, al chat ni a la sincronización de Qdrant. No comprueba la navegación ni atribuye una causa a una pantalla antigua del navegador. Los registros históricos del paciente temporal se mantienen por el diseño de auditoría y respaldos; no se manipularon directamente por SQL.

El [verificador](backend_cruzado.py) conserva sus resultados sin sobrescribirlos. Para una nueva ejecución necesita destinos de evidencia nuevos; no se vuelve a ejecutar automáticamente contra los mismos archivos.
