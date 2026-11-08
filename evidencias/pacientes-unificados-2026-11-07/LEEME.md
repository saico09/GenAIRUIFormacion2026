# Pacientes compartidos y registros · 07/11/2026

Ahora un paciente creado en Python aparece también en Java y en la página 02 Pacientes. Ambas APIs usan `public.patients`; ya no se mantienen dos listas independientes. Cada alta crea su Markdown y respaldo. `public.patient_diseases` guarda el mismo UUID, enfermedad, tratamiento y medicamento del informe, y permite crear, consultar, editar y borrar esos registros por cualquiera de las dos APIs.

`public.medical_consultations` conserva consultas y copias completas del informe. `public.transaction_logs` guarda una fila por operación HTTP, con un único UUID `id` y `patient_id` cuando corresponde. Los respaldos y logs sobreviven al borrado del paciente; sus referencias históricas no llevan borrado en cascada.

Es una ampliación pedida por Marco. No añade HDU, horas o requisitos atribuidos al plan original de Rui. Fuente funcional: **`7d591cefbeb8354d8c65bb3cc87adb461addb435`**. El commit **`089c56a3373fd1259e9fd21ca7825677a7ccbd86`** actualiza después las pruebas de auditoría, sin cambiar el runtime. Ambos están incluidos en la implementación publicada **`c66a595c0b3b21e95ac7e3a8e0a511988b4ae068`**. La prueba GitOps y el cierre del entorno del 08/11 se detallan abajo. El SHA del cierre documental se registra en el contexto local, fuera del repo.

## Qué quedó comprobado

| Prueba | Resultado y evidencia |
|---|---|
| Migración y conservación | Se cotejaron las cinco filas Python, las tres equivalentes Java, 65 registros históricos y 474 logs previos. Se conservaron sus columnas originales y los IDs. Esos números son el corte anterior, no los totales después de generar evidencia. [Resultado](migracion-conservacion.json). |
| CRUD cruzado y consistencia | **66 peticiones/66 filas de auditoría**. Diez altas concurrentes sin pérdida, UUID estable, aislamiento entre pacientes, validaciones, renombre, diario intacto y borrado. [Resultado](cruzado-java-python.json). |
| Rollback de verdad | Dentro del caso anterior, un trigger diferido provocó seis errores de COMMIT: agregar, renombrar y borrar por ambas APIs. Se restauraron SQL y Markdown antes de liberar el bloqueo compartido. El trigger y los pacientes propios quedaron retirados. |
| Contrato Java anterior | **37 peticiones**, diez bloques: consultas, reintento, conflicto 409, revisión del informe, edición A→B→A, restauración desde SQL y recorte de auditoría. Sumadas al cruce anterior son **103 HTTP**. [Resultado](java-consultas.json). |
| Python sin Java | **17 peticiones** con base nueva y **14 peticiones** de auditoría aislada; también se comprobó la adaptación S1. [Python](python-fresh.json), [auditoría](python-auditoria-fresh.json), [S1](python-s1-fresh.json). |
| Carga inicial | Base vacía, identidades/UUID inválidos rechazados, dos inicializadores concurrentes, rollback de filas/secuencia, repetición sin duplicar ni recrear pacientes borrados. [Integración](bootstrap-compartido.json), [Python](python-bootstrap-fresh.json). |
| Contratos sin LLM | **57 comprobaciones** de parser, corpus, almacenamiento y auditoría. [Resultado](contratos-final.json). |
| Arranque, montaje y auditoría ASGI | **25/25 unittest**: cuatro casos del marcador, ocho de arranque/reintentos y trece de auditoría. Las cabeceras de correlación se conservan pero no se persisten como UUID adicionales en SQL. Con marcador ausente no se crea una carpeta local ni se modifica el informe previo. [Suite completa](unittest-completo.json), [guard aislado sin red ni datos](guard-montaje-tests.json). |
| Navegador real | **6/6 bloques sin mocks**: paciente compartido, formulario, confirmaciones, edición/conflicto, borrado, exploradores y ancho 390 px. Los hashes anteriores/posteriores coinciden tras limpiar el temporal. [Resultado](ui-real/resultados.json). |
| RAG y consultas | **14/14 casos de lectura con el prompt final**, conservando historias y vectores; **4/4 consultas HTTP** y siete comprobaciones de guardado, reintento, propuestas y trazas/logs. La comprobación de trazas añadió una quinta consulta del temporal y verificó raíz+cuatro hijos y siete eventos Loki. [Corpus](rag-real-final.json), [HTTP](consultas-rag-guardado-final.json), [traza](regresion-traza.json). |

El problema inicial de los informes 4/24 era de permisos: Python creaba archivos 0600 como usuario 0 y Java usaba 10001. Ambas imágenes usan ahora 10001; se reparó sólo el propietario de esos dos archivos, conservando sus hashes. [Comprobación](permisos-md.json).

## Qué aprendimos del fallo de RAG

La primera regresión HTTP falló en dos casos aunque el ensayo de lectura del corpus había pasado: al recibir un relato nuevo o preguntar por síntomas anteriores, el modelo contestaba una pregunta vieja incluida en el contexto. No bastaba con comprobar que la cita existía.

El prompt ahora distingue la pregunta actual del material recuperado y deja explícito que las preguntas antiguas son datos del historial. El [replay de esos dos casos](rag-prompt-replay.json) pasó y después se repitieron los cuatro casos mediante la API real, más los catorce del corpus, con el resultado indicado arriba. Se conservan el [primer fallo](consultas-rag-guardado.json) y sus [salidas originales](rag-fallo-raw.json), para no esconder la incidencia. La muestra usa datos sintéticos y no demuestra exactitud clínica general.

El primer intento del verificador cruzado también rechazó un email de prueba con dominio `example.invalid`; se corrigió el fixture a `example.com`, sin cambiar la validación del producto. [Registro](cruzado-fixture-email-invalido.json).

## Para repetir lo principal

Desde `codigo`, con el Compose principal levantado:

```powershell
python scripts/verificar_unificacion_java.py --postgres-container genairuiformacion2026-postgres-1 --output evidencias/pacientes-unificados-2026-11-07/cruzado-nueva-ejecucion.json
```

Ese verificador usa dos pacientes propios y un trigger limitado a uno de ellos, y los retira al terminar. Para repetir las consultas reales, incluido el guardado y la traza:

```powershell
python scripts/verificar_consultas_regresion.py --trace --output evidencias/pacientes-unificados-2026-11-07/consultas-nueva-ejecucion.json
```

Para los contratos rápidos, sin consultar al modelo:

```powershell
Get-Content -Raw scripts/verificar_contratos_historia.py | docker compose exec -T python-api python -
Get-Content -Raw scripts/verificar_rag_corpus_realista.py | docker compose exec -T python-api python -
Get-Content -Raw scripts/verificar_contratos_unificacion.py | docker compose exec -T python-api python -
```

## Entregas semanales y cierre del entorno

Las **diez pilas Compose completas pasaron**, una por vez, con los mismos puertos 8000/8080: **170 peticiones CRUD, 91 de Postman, 14 comparaciones de chat y la interfaz en siete semanas**. El verificador externo copia en memoria los IDs devueltos por sus POST; la colección no lleva scripts. Las copias quedaron detenidas con sus volúmenes conservados. Al restaurar el principal coincidieron los cinco pacientes, cinco Markdown y 13 puntos Qdrant; SonarQube se conservó. [Resultado por semana y restauración](semanas.json).

**GitOps principal también pasó el 08/11:** seis bloques reales comprobaron el montaje compartido entre las dos réplicas y Compose, CRUD cruzado, respuesta 503 sin marcador, recuperación tras perder el proceso 9p, stop/start y conservación del diario al borrar registros. Argo verificó `c66a595` como Synced/Healthy/Succeeded con dos pods Ready. Los cinco pacientes, cinco informes y sus filas SQL previas conservaron sus hashes; se retiró el temporal. [Ensayo integral](gitops/montaje-real.json).

El primer intento del verificador se quedó esperando la salida de un proceso ya terminado; era compatible con handles heredados por servidores de fondo. Se cambió la captura a archivos temporales y se repitió todo, sin afirmar que se inspeccionó cada handle. [Intento interrumpido y limpieza](gitops/ensayo-harness-interrumpido.json).

Los helpers GitOps de S9/S10 tienen revisión estática; no se ejecutó Minikube/Argo dentro de las copias semanales. El [cierre final](cierre-entorno.json) pasó **siete bloques**: ocho URLs HTTP 200, dos targets UP, cinco pacientes, cinco Markdown y trece puntos Qdrant conservados, más SQL alineado con los informes. Quedaron operativos los nueve servicios principales; las diez pilas semanales y `genai` quedaron detenidos. Python se recreó expresamente y se cotejaron sus 33 archivos de código con la fuente documentada; los otros ocho contenedores y SonarQube conservaron sus IDs.

La primera lectura de Loki devolvió 503 y la siguiente 200, sin reinicios. Se conserva ese [primer resultado](cierre-entorno-loki-transitorio.json); no se identificó una causa interna. El control final sólo lee HTTP, SQL, archivos e inventario: no acredita otro arranque ni otra inferencia.

Drive ya tiene los nueve Word actualizados y releídos, con IDs/carpetas/permisos conservados; S6 queda intacta y se presenta junto con S7. Postman instalado conserva diez carpetas y las cinco peticiones personales: 96 peticiones, sin scripts ni variables; health de Semana 10 respondió 200. En los ejemplos CRUD se copia el ID/UUID devuelto por POST sobre los marcadores 0/UUID; no hay encadenamiento automático. El reemplazo de colección generó un ID nuevo en Postman. Las evidencias de esas entregas están fuera del repo, en `dailys/_herramientas/drive-pacientes-unificados-verificado-2026-11-07.json` y `dailys/postman/IMPORTACION_SIMPLE_VERIFICADA_2026-11-07.json`.

SQL y archivos tienen compensación para los errores probados; no se afirma una transacción distribuida resistente a cualquier cierre forzado entre escrituras. Ninguna comprobación técnica acredita horas personales, asistencia o evaluación de Rui.
