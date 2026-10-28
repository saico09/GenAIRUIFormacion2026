# Historial de la app

Qué se ha ido agregando, qué es y cómo se usa. Lo más nuevo arriba. Comandos completos en [GUIA.md](GUIA.md).

Cada entrada cuenta lo que había en esa fecha; las limitaciones antiguas pueden estar resueltas en una entrada posterior. El estado actual se resume en [README.md](README.md).

## HDU-018 · 28/10/2026 · Espera y reintento en el chatbot

- **Cargando y botón desactivado** mientras llega la respuesta; `finally` restaura ambos al terminar, también si ocurre un error.
- **Pregunta vacía** muestra `Escribe una pregunta` y se comprobó que no hace ningún POST `/chat`.
- **Ollama realmente detenido** produjo 503 `LLM no disponible`, conservando el texto. Tras iniciar Ollama con el script, Consultar funcionó en la misma página: dos respuestas, Alfa y fuente correcta.
- **Evidencias UI** en `evidencias/S04-ui-018.json` y las capturas de error/reintento. La explicación personal sigue pendiente.

## HDU-017 · 28/10/2026 · Chatbot en el navegador

- **`python-api/app/static/index.html`** se abre en `http://localhost:8000`: selector de pacientes, pregunta y columnas Sin RAG / Con RAG con fuentes.
- **Selector conectado a `GET /patients`** y envío a `POST /chat` con el paciente elegido y la pregunta exacta. Las respuestas se muestran como texto.
- **Prueba real con Ana en Edge**: 200, Enfermedad Alfa en RAG y fuente `paciente-1.md / Enfermedad`; la rama directa reconoció falta de datos.
- **Captura y respuesta** en `evidencias/S04/comparacion.png` y `S04-ui-017.json`. La comprensión personal sigue pendiente.

## HDU-016 · 28/10/2026 · Comparación directa y RAG

- **`python-api/rag.py`** recupera hasta dos fragmentos del paciente y arma el prompt con texto, archivo y sección. Pide citar la fuente y reconocer los datos ausentes.
- **`POST /chat`** devuelve `direct_answer`, `rag_answer` y `sources`; conserva la misma pregunta, `llama3.2:3b` y temperatura 0 en ambas ramas.
- **Dos casos reales comprobados**: Ana → Enfermedad Alfa con `[paciente-1.md/Enfermedad]`; cirugía → `No hay información suficiente.`. La rama directa reconoció falta de datos en ambos casos.
- **`scripts/verificar_chat.py`** repite esos casos. `evidencias/S04-rag.json` conserva prompts, modelo, parámetros, respuestas y fuentes; la cita y la respuesta salen del modelo.
- Ojo: el 503 `Qdrant no disponible` se probó con una API aislada y URL inaccesible, sin detener Qdrant real. La comprensión personal del flujo sigue pendiente.

## HDU-015 · 28/10/2026 · Respuesta directa del LLM

- **`llama3.2:3b`** descargado en Ollama y probado con `Responde hola`. Se mantiene separado de `nomic-embed-text`, que genera los vectores.
- **`app/llm.py`** centraliza la llamada: temperatura 0, contexto 2048, salida máxima de 256 tokens y timeout de 120 segundos; el modelo sale de `CHAT_MODEL` en Compose.
- **`POST /chat`** recibe paciente y pregunta y devuelve `direct_answer` enviando solo la pregunta. La prueba de Ana respondió 200 y reconoció que no tenía información, sin inventar enfermedad.
- **Errores comprobados**: pregunta vacía → 422, paciente inexistente → 404 y Ollama realmente detenido → 503 `LLM no disponible`. El script de inicio levantó de nuevo el servidor correctamente.
- Ojo: en esta HDU la respuesta todavía no usa documentos ni Qdrant. La explicación personal sigue pendiente; las respuestas y parámetros están en `evidencias/S04.md`.

## HDU-014 · 28/10/2026 · Recuperación y persistencia Qdrant

- **`scripts/verificar_recuperacion.py`** coteja los nueve payloads y repite las cuatro preguntas: tres respuestas presentes, cirugía ausente y ocho resultados del paciente correcto.
- **Reinicio de Qdrant comprobado**: antes y después quedaron nueve puntos, tres por paciente, sin repetir la ingesta. Fuentes, textos y scores se conservaron.
- **Código y evidencias** guardados en el commit `c0c62e5`; S03 incluye los resultados y tres frases para repasar vectores, filtro por paciente y límites de similitud.
- Ojo: la explicación personal de Marco y la revisión de Rui siguen pendientes; la comprobación técnica no acredita una sesión recibida.

## HDU-013 · 28/10/2026 · Buscar dos fragmentos del paciente

- **`python-api/buscar.py`** recibe id y pregunta; comparte `search_fragments()` de `app/knowledge.py` y el modelo de embeddings usado en la ingesta.
- **Filtro por `patient_id` y máximo dos resultados**: devuelve score, paciente, archivo, sección y texto. Las cuatro preguntas se comprobaron sin mezclar pacientes.
- **Tres respuestas conocidas recuperadas**: Enfermedad Alfa, Tratamiento Beta y Medicamento Gamma aparecieron en el primer resultado de su consulta.
- Ojo: preguntar por cirugía de Ana recuperó Enfermedad y Tratamiento, que no contestan esa pregunta. Similitud no prueba que exista respuesta; todavía no interviene un LLM.

## HDU-012 · 28/10/2026 · Ingesta sin duplicados

- **`python-api/ingestar.py`** lee los tres Markdown, separa las nueve secciones y genera sus embeddings antes de guardarlos en `historias`.
- **UUID estable por paciente y sección**: repetir la carga actualiza el mismo punto; conserva `patient_id`, `source`, `section` y `text` para reconocer su origen.
- **Dos ejecuciones comprobadas** terminaron con nueve puntos, tres por paciente, y todos los ids y payloads iguales a los documentos. Los datos quedan en `qdrant_data`.
- Ojo: no se borran puntos para forzar un resultado correcto; si el cotejo falla, el script avisa. La búsqueda y la prueba tras reiniciar Qdrant vienen en las HDU siguientes.

## HDU-011 · 28/10/2026 · Embeddings y colección Qdrant

- **Reanudación autorizada por Marco** aunque no se alcance el mínimo documental de RAM. Se arrancó Docker Desktop y las comprobaciones de esta HDU pasaron; el bloqueo de HDU-010 queda como antecedente.
- **Qdrant 1.20.0** se añadió a Compose en `localhost:6333`, con datos en `qdrant_data`. La consulta de colecciones responde 200.
- **Ollama 0.40.12 para Windows** quedó instalado desde el ZIP oficial en la carpeta local de programas. `scripts/iniciar_ollama.ps1` lo inicia o reutiliza; no se cambió el PATH global.
- **`nomic-embed-text`** descargado y probado desde `python-api`: genera vectores de 768 componentes. `EMBEDDING_MODEL` centraliza la elección y `app/knowledge.py` la comparte.
- **`preparar_vectores.py`** crea `historias` solo si falta y comprueba dimensión 768 y distancia Cosine; una configuración incompatible se informa sin borrar la colección.
- Ojo: ingesta y búsqueda siguen en las HDU siguientes; todavía no se acredita RAG por disponer de un vector y una colección.

## HDU-010 · 28/10/2026 · Historias y preguntas ficticias

- **`datos/paciente-1.md`, `paciente-2.md` y `paciente-3.md`** contienen nueve secciones: Enfermedad, Tratamiento y Medicamento para Ana, Bruno y Carla. Usan valores ficticios Alfa/Beta/Gamma y los ids Python 1, 2 y 3 comprobados por HTTP.
- **`datos/preguntas.json`** guarda las cuatro preguntas del checklist y sus respuestas esperadas. Tres se responden con los documentos; la última cirugía de Ana no aparece y debe responderse `No hay información suficiente`.
- **Datos listos para futura ingesta**: la guía permite leer los archivos; las comprobaciones están en `evidencias/S03.md`. Todavía no se implementaron embeddings ni RAG.
- Ojo en el primer intento: HDU-011 quedó bloqueada antes de instalar Ollama/Qdrant. La medición dio 0,32 GB libres de 13,86 GB, frente al mínimo de 8 GB. Después Marco autorizó continuar; la reanudación y sus pruebas están en HDU-011.

## HDU-009 · 28/10/2026 · Persistencia Java y repaso de equivalencia

- **Prueba de persistencia con `-Servicio java-api`** reinicia Java y PostgreSQL y compara sus pacientes antes/después. Conservó las tres filas y los cuatro campos originales de Ana, sin borrar `pgdata`.
- **Python conservado**: tras ese reinicio, la consulta de Ana en FastAPI respondió 200.
- **Errores después del reinicio**: Java siguió rechazando el email sin arroba con 422 y respondió 404 al consultar el id ausente 999999.
- **Guía y evidencias S02** dejan el comando reproducible y el resultado, junto con el recorrido controlador → JPA → PostgreSQL para repasar.
- Ojo: la explicación de Marco y la revisión de Rui están pendientes. No se registra una cita ni una revisión recibida por haber terminado las pruebas técnicas.

## HDU-008 · 28/10/2026 · Comparar el contrato de las dos APIs

- **Verificador ampliado** a 14 entradas inválidas, probadas en POST y PUT: 28 respuestas 422 por API, 56 entre ambas. Cada error conserva las filas anteriores.
- **Contrato comprobado**: 201 al crear, 200 al listar/consultar/editar, 204 vacío al borrar y 404 para ids ausentes. Los cuatro campos de respuesta coinciden con lo enviado.
- **Email Java corregido**: aceptaba `ana@localhost` y `ana@com`; ahora los rechaza con 422, como Python, mediante una restricción de dominio completo.
- **Resultados guardados** en `evidencias/S02.md` y las salidas `S02-crud-python.txt` / `S02-crud-java.txt`. Quedaron intactas las cuatro filas Python y las tres Java, sin temporales.
- Ojo: la equivalencia comprobada cubre estos casos y el contrato HTTP. Los detalles internos de los errores 422 pueden diferir entre frameworks; no se exige el mismo mensaje.

## HDU-007 · 28/10/2026 · Editar y borrar pacientes en Java

- **`PUT /patients/{id}`** actualiza los tres campos y responde 200. `@Transactional` mantiene búsqueda y cambios en la misma transacción; JPA los guarda al confirmar.
- **`DELETE /patients/{id}`** borra el paciente y responde 204 sin cuerpo. GET, PUT y DELETE comparten `findPatient()` y devuelven 404 si no existe.
- **Verificador CRUD común** probado contra Java: creó el temporal id 4, cambió sus tres campos, lo borró y comprobó el 404 posterior. Los tres pacientes originales quedaron intactos.
- **Errores comprobados**: id 999999 devuelve 404 en las tres operaciones y los seis casos inválidos de POST/PUT devuelven 422 sin cambios en las filas.
- Ojo: la comparación detallada entre las APIs continúa en HDU-008; estos resultados cubren los casos básicos del CRUD.

## HDU-006 · 28/10/2026 · Crear y consultar pacientes en Java

- **`POST /patients` en Java** guarda los mismos tres campos JSON que Python y responde 201. `PatientRequest` valida la entrada y `PatientResponse` conserva los nombres del contrato, incluido `birth_date`.
- **`GET /patients` y `GET /patients/{id}`** devuelven 200 con los datos guardados. El listado sale ordenado por id; un id inexistente responde 404.
- **Ana, Bruno y Carla Demo** se cargaron desde `datos/pacientes.json` y quedaron con ids Java 1–3. Sus tres campos coinciden con Python; los ids se generan por separado en cada tabla.
- **Validaciones comprobadas**: nombre de espacios, fecha imposible y email sin arroba responden 422 sin modificar las tres filas Java. Python conservó sus cuatro filas.
- Ojo: en este punto editar y borrar en Java seguía pendiente de HDU-007. Repetir la carga de los tres pacientes crea duplicados.

## HDU-005 · 28/10/2026 · Spring Boot conectado a PostgreSQL

- **`java-api/`** agrega el segundo servicio: Spring Boot 4.1.2, Maven 3.10.0 y Temurin Java 27. El build en Docker terminó correctamente y el arranque comprobó acceso a PostgreSQL.
- **`GET /health` en `localhost:8080`** responde 200 con `{"status":"ok"}`. FastAPI sigue disponible en el puerto 8000.
- **`java.patients`** separa las filas de Java de las de Python, que siguen en `public.patients`. Al comprobar esta HDU, Java tenía cero filas y Python conservaba cuatro.
- **Contenedor Java** corre con usuario 10001, un límite de 512 MiB y heap de 64–256 MiB; se observó un consumo de unos 263 MiB.
- Ojo: en esta HDU quedó conexión y health. El CRUD Java todavía no formaba parte de lo verificado; la explicación de Marco continúa pendiente.

## HDU-004 · 28/10/2026 · Persistencia y repaso del CRUD Python

- **`scripts/verificar_persistencia.ps1`** reinicia PostgreSQL y FastAPI y compara las filas antes/después. Se probó con cuatro filas: todas se conservaron y Ana mantuvo sus cuatro campos.
- **`pool_pre_ping=True`** en `db.py` comprueba la conexión antes de reutilizarla y descarta las que quedan viejas tras reiniciar PostgreSQL.
- **CRUD repetido después del reinicio**: crear, consultar, editar, borrar, 404 y seis casos 422 correctos; la base volvió a quedar con las cuatro filas previas.
- **Guía y evidencias** dejan el comando para repetir la prueba y el recorrido del dato para repasar el código.
- Ojo: la revisión de Rui y la explicación de Marco están pendientes. Registrar ese pendiente no crea una cita ni acredita una demo o revisión recibida.

## HDU-003 · 28/10/2026 · Editar, borrar y responder errores

- **`PUT /patients/{id}`** reemplaza nombre, fecha de nacimiento y email; devuelve 200 con el paciente actualizado. Usa las mismas validaciones que POST.
- **`DELETE /patients/{id}`** borra el registro y devuelve 204 sin cuerpo. Los comandos de la guía trabajan con un paciente temporal para conservar los anteriores.
- **`find_patient()`** comparte la búsqueda entre GET, PUT y DELETE; un id inexistente ahora devuelve 404 con `Paciente no encontrado`.
- **`scripts/verificar_crud.py`** comprueba el ciclo completo, los errores 404/422, el 204 vacío y que los pacientes previos queden intactos. Se ejecuta desde PowerShell con el Python del contenedor.
- **`README.md`** reúne el arranque, contrato HTTP y un comando por operación. **Python 3.15.2** quedó fijado en Docker y se comprobó el build y `pip check`; PostgreSQL conserva 18.6.
- Ojo: las comprobaciones técnicas pasaron; la explicación de Marco y la revisión con Rui siguen pendientes. No se da por recibida una revisión ni por completada la formación por tener código funcionando.

## HDU-002 · 27/10/2026 · Crear y consultar pacientes

- **Tabla `public.patients`** (id autogenerado, name, birth_date, email). La crea la API al arrancar si no existe; no borra datos.
- **`POST /patients`** guarda un paciente y responde 201 con su id. **`GET /patients`** lista todos y **`GET /patients/{id}`** trae uno.
- **Validaciones** en `app/schemas.py`: name no vacío, birth_date `YYYY-MM-DD` de una fecha real y email válido. Si algo falla, responde 422 y no guarda nada.
- **Código separado**: `db.py` conexión (variables de entorno), `models.py` la tabla, `schemas.py` validaciones, `main.py` endpoints.
- **`datos/pacientes.json`**: Ana, Bruno y Carla Demo (ficticios). Ya cargados: ids 1, 2 y 3.
- Ojo en ese momento: un id que no existía daba 500. Se corrigió a 404 en la HDU-003.

## HDU-001 · 27/10/2026 · PostgreSQL + FastAPI en Docker

- **codigo/** es el repo de Git; todo lo de la app vive ahí, separado de los documentos del programa.
- **compose.yml**: levanta dos servicios con `docker compose up -d --build`.
- **postgres** (18.6-alpine): base `genai`. Usuario y clave salen del `.env` (no va a Git). Los datos viven en el volumen `pgdata`, así que sobreviven a un `down`. Tiene healthcheck con `pg_isready`. Publicado en `localhost:5432` (solo este equipo) para entrar con DBeaver.
- **python-api** (Python 3.15 + FastAPI): por ahora solo `GET /health`, que responde `{"status":"ok"}` en http://localhost:8000. Espera a que postgres esté sano antes de arrancar. Ya trae instaladas SQLAlchemy, psycopg y email-validator para el CRUD de la HDU-002, pero todavía no se conecta a la base.
- **.env.example**: los nombres de las variables, sin valores. Se copia como `.env`.
- **datos/** vacía (los pacientes llegan en la HDU-002). **evidencias/S01.md** guarda las pruebas.
- Ojo: el equipo tiene 1,2 GB de RAM libre y el programa pide 8. Resolverlo antes de S3.
