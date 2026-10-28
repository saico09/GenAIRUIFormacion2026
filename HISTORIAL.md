# Historial de la app

Qué se ha ido agregando, qué es y cómo se usa. Lo más nuevo arriba. Comandos completos en [GUIA.md](GUIA.md).

Cada entrada cuenta lo que había en esa fecha; las limitaciones antiguas pueden estar resueltas en una entrada posterior. El estado actual se resume en [README.md](README.md).

## HDU-029 · 28/10/2026 · Métricas revisadas

- **GET 200 y 404 repetidos en ambas APIs**: cada petición sumó exactamente uno en sus contadores; Prometheus recogió los valores nuevos sin modificar pacientes.
- **Seis paneles comprobados** mediante Grafana, con tráfico, porcentaje de errores y p95 finitos; dashboard exportado y dos capturas inspeccionadas en `evidencias/s06/revision.md`.
- **`scripts/verificar_dashboard.cjs`** permite repetir la consulta y guardar capturas. La guía incluye sus comandos locales y las frases de apoyo para explicar los cálculos.
- Ojo: la explicación propia de Marco y la revisión de Rui siguen pendientes. Los resultados son una lectura de esa ventana de cinco minutos, no una garantía de rendimiento.

## HDU-028 · 28/10/2026 · Latencia p95 y carga comprobada

- **Dos paneles p95** completan las filas del dashboard, con unidad segundos y cálculo sobre los buckets de los últimos cinco minutos.
- **`scripts/generar_trafico.py`** hizo 20 GET 200 y 5 GET 404 por API, distribuidos en unos dos minutos: 50 respuestas esperadas, sin modificar pacientes.
- **Seis paneles con datos numéricos** y capturas inspeccionadas; últimos p95 observados de 0,004760 s en FastAPI y 0,009647 s en Spring Boot. Resultados en `evidencias/s06/028-latencia.md` y dashboard exportado en esa carpeta.
- Ojo: p95 es una estimación desde buckets del servidor, no el tiempo de red del script ni una garantía de rendimiento. La guía usa la ruta Python real del equipo.

## HDU-027 · 28/10/2026 · Dashboard de tráfico y errores

- **Dashboard APIs GenAI** provisionado desde `observabilidad/dashboard.json`, con una fila por API y cuatro paneles: tráfico en req/s y errores 4xx/5xx en porcentaje.
- **Ventana de cinco minutos** y expresión Grafana `100 * $B / $A`, usando B como tasa de errores y A como tasa total. El dashboard muestra inicialmente quince minutos.
- **Cuatro paneles comprobados** mediante la API de Grafana, incluida su expresión matemática: valores finitos tras GET 200/404 en ambas APIs; captura inspeccionada en `evidencias/s06/consultas.md`.
- Ojo: sin tráfico puede no haber porcentaje definido. Health y consultas a métricas también cuentan; dos peticiones aisladas no obligan a mostrar 50 %.

## HDU-026 · 28/10/2026 · Java, Prometheus y Grafana conectados

- **Actuator y Micrometer** exponen `/actuator/prometheus` en Java, con contador e histograma HTTP. GET 200/404 sumaron exactamente uno por status y mantuvieron la ruta normalizada.
- **Prometheus 3.15.1** recoge ambas APIs cada 15 segundos; targets `fastapi` y `springboot` comprobados UP, con la etiqueta service en las series.
- **Grafana 13.3.0** tiene la fuente Prometheus provisionada; el clic real en Save & test pasó. Puertos locales 9090 y 3000, volúmenes propios y versiones/digests fijados.
- **Usuario admin y clave local** en `GRAFANA_ADMIN_PASSWORD` de `.env`; el ejemplo la deja vacía para completar en clones nuevos. No se guarda el secreto en Git ni evidencias.
- **Evidencia** en `evidencias/s06/026.md`, con targets y captura de Grafana. La comprobación técnica no acredita explicación personal ni revisión experta.

## HDU-025 · 28/10/2026 · Métricas HTTP en FastAPI

- **`app/metrics.py` y prometheus-client 0.26.0** exponen `GET /metrics`: contador de peticiones e histograma de duración en segundos.
- **Etiquetas acotadas**: método, ruta y status. Los pacientes usan `/patients/{id}` y las rutas desconocidas `unmatched`, sin una serie por URL o paciente.
- **`scripts/verificar_metricas.py`** comprobó GET 200/404 e incremento exacto de uno en contador y count del histograma por status, sin modificar datos. Evidencia en `evidencias/s06/fastapi.md`.
- Ojo: los contadores se reinician con el proceso e incluyen las consultas a `/metrics`. En esta HDU se comprobó la exposición de métricas; la recolección y el dashboard vienen después.

## HDU-024 · 28/10/2026 · Preparación de demo comprobada

- **Comprobación previa repetida**: health y Ana responden 200 en ambas APIs; el chatbot devuelve Alfa con fuente y cirugía sin información.
- **`evidencias/S05-validacion.md`** enlaza resultados y capturas y deja explícito el estado: Validación pendiente. No hay valoración 1–4 ni correcciones expertas recibidas.
- Ojo: las frases del ensayo son apoyo; siguen pendientes las frases propias de Marco, la demo/explicación con Rui y el ciclo completo desde detenido. No se acreditan horas ni una sesión realizada.

## HDU-023 · 28/10/2026 · Ensayo y espera de disponibilidad

- **`scripts/esperar_apis.ps1`** espera health de ambas APIs hasta 90 segundos. Se añadió tras un `Empty reply from server`: Compose había terminado, pero Python todavía arrancaba.
- **Arranque repetido con la espera**: health y Ana 200 en ambas APIs, nueve puntos Qdrant y Ollama disponible. README, guía y guion incluyen el paso corregido.
- **Recorrido ensayado**: ambos CRUD, reinicios de PostgreSQL/APIs, dos búsquedas y cuatro preguntas HTML pasaron; cuatro filas Python y tres Java quedaron intactas.
- **`evidencias/S05-ensayo.md`** guarda resultados, capturas y seis frases de apoyo ligadas al código. No reemplazan una explicación personal.
- Ojo: el ciclo completo desde detenido sigue NO EJECUTADO; comprensión de Marco y revisión de Rui continúan pendientes.

## HDU-022 · 28/10/2026 · Guion de demo de etapa 1

- **`evidencias/S05-guion.md`** ordena arranque, CRUD Python/Java, reinicio de PostgreSQL y APIs sin borrar volúmenes, búsqueda y chatbot.
- **Comandos y resultados esperados** enlazados con código y evidencia; los CRUD crean, editan y borran su propio Test Demo, conservando a Ana, Bruno y Carla.
- **Dos preguntas fijas de demo**: enfermedad de Ana → Alfa con fuente; cirugía de Ana → falta de información. Se mantienen pregunta, modelo y parámetros entre ambas ramas.
- Ojo: el ensayo conjunto corresponde a HDU-023; el ciclo completo desde detenido y la validación humana siguen pendientes. El guion no vuelve a intentar la parada rechazada de Qdrant.

## HDU-021 · 28/10/2026 · Repetición y pendientes concretos

- **Ambos CRUD repetidos**: códigos correctos, 56 respuestas 422 esperadas y cuatro filas Python / tres Java intactas, sin temporales.
- **Cuatro preguntas repetidas en HTML**: Alfa, Beta, Gamma y cirugía sin información; se inspeccionaron respuestas, fuentes y capturas. No hizo falta cambiar la aplicación.
- **`evidencias/S05-pendientes.md`** conserva el resultado de cada repetición y el ciclo completo desde detenido como NO EJECUTADO; no se presenta como fallo de la app ni como corrección realizada.
- Ojo: siguen pendientes la explicación personal y la revisión de Rui; no se registra una sesión ni valoración recibida.

## HDU-020 · 28/10/2026 · Arranque y comprobación de etapa 1

- **README seguido en el entorno existente**: Compose y Ollama disponibles, health y Ana correctos en ambas APIs, nueve puntos en Qdrant.
- **CRUD y dos consultas HTML comprobados**: temporales eliminados, filas anteriores conservadas, Alfa con fuente y cirugía sin información.
- **`--demo` y carpetas de evidencia** en el verificador UI permiten ensayar los dos casos de Ana sin sobrescribir S04. Resultados en `evidencias/S05-arranque.md`.
- Ojo: detener todo y arrancar desde detenido quedó NO EJECUTADO por el rechazo automático previo de la parada de Qdrant. Compose lo recreó automáticamente durante `up` y conservó nueve puntos; eso no completa el ciclo pendiente.

## HDU-019 · 28/10/2026 · Cuatro preguntas comprobadas desde HTML

- **Dataset completo en Edge**: cuatro POST exactos y 200. RAG respondió Enfermedad Alfa, Tratamiento Beta, Medicamento Gamma y `No hay información suficiente.` para cirugía; la directa reconoció falta de datos.
- **Respuestas y fuentes visibles** cotejadas contra el JSON, siempre del paciente elegido. Se conservaron el modelo, parámetros, textos y recuperación.
- **Campos bloqueados durante la espera** y paciente consultado identificado en el resultado, para evitar confundir una respuesta con otro paciente. Se comprobó también su restauración al terminar.
- **`scripts/verificar_chat_ui.cjs --dataset`** repite los casos; la guía deja el comando usado en este equipo. Respuestas y cuatro capturas inspeccionadas en S04.
- Ojo: las frases de apoyo de S04 son para repasar; no acreditan una explicación de Marco ni revisión recibida de Rui. Ambas siguen pendientes.

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
