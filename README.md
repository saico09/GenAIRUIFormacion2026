# GenAI · app de práctica

Por ahora tenemos PostgreSQL, dos servicios de pacientes —FastAPI y Spring Boot— y una comparación de respuestas con y sin RAG. Ollama genera embeddings y respuestas; Qdrant guarda las nueve secciones de las tres historias ficticias. Ambas APIs permiten crear, listar, consultar, editar y borrar pacientes. Los comandos son para PowerShell, desde esta carpeta `codigo`, con Docker Desktop abierto.

[Guía de comandos](GUIA.md) · [Qué se ha agregado](HISTORIAL.md) · [Evidencias S01](evidencias/S01.md) · [Evidencias S02](evidencias/S02.md) · [Evidencias S03](evidencias/S03.md) · [Evidencias S04](evidencias/S04.md) · [Trello](https://trello.com/b/DKjKsa6B/ckd-genairuiformacion2026)

Para recorrer la etapa 1, usa el [guion de demo](evidencias/S05-guion.md): arranque, ambos CRUD, persistencia, búsqueda y chatbot. El [ensayo HDU-023](evidencias/S05-ensayo.md) pasó sobre el entorno existente después de añadir la espera de disponibilidad de las APIs; conservó cuatro filas Python, tres Java y nueve puntos Qdrant. La [comprobación previa HDU-024](evidencias/S05-validacion.md) también pasó. **La explicación personal, la demo con Rui y su valoración siguen pendientes.**

El ciclo completo de detener todo y arrancarlo desde detenido sigue **NO EJECUTADO** por un rechazo automático previo al detener Qdrant. Su recreación automática en HDU-020 conservó nueve puntos, pero no acredita ese ciclo. Detalles en [arranque](evidencias/S05-arranque.md) y [pendientes](evidencias/S05-pendientes.md).

El [control HDU-038](evidencias/s08/control.md), comprobado el 28/10/2026, reúne el estado por componente y una misma pregunta de Ana en métricas, logs y trazas: HTTP 200, cinco spans y siete logs. El contador POST `/chat` 200 pasó de 1 a 2; los paneles son métricas agregadas, no tiempos de esa consulta individual.

El calendario conserva el **receso del 21/12/2026 al 01/01/2027, sin tareas ni recuperación de pendientes dentro de ese período**. La primera acción prevista para el **04/01/2027** es seguir [Arrancar](#arrancar), esperar ambas APIs y comprobar sus health; después consultar a Ana y repetir una pregunta RAG con la [guía de regreso](GUIA.md#retomar-después-del-receso). El ciclo completo desde detenido y la validación humana continúan pendientes; estas fechas son planificación, no una sesión confirmada.

## Arrancar

preparar la configuración solo en un clon nuevo (después completa los valores de `.env`; si ya existe, lo conserva):

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

En un clon nuevo, completa `POSTGRES_USER`, `POSTGRES_PASSWORD` y `GRAFANA_ADMIN_PASSWORD` en `.env` antes de arrancar. La clave de Grafana ya está configurada en este equipo; se queda solo en ese archivo local.

levantar postgres, las dos apis, qdrant, prometheus, grafana, loki, alloy y phoenix:

```bash
docker compose up -d --build
```

esperar a que ambas apis respondan (hasta 90 segundos):

```powershell
.\scripts\esperar_apis.ps1
```

Compose puede terminar antes de que las APIs acepten peticiones. Este paso evita consultar mientras todavía arrancan; si vence el plazo, avisa qué API no quedó lista.

iniciar Ollama en Windows (ya instalado en este equipo):

```powershell
.\scripts\iniciar_ollama.ps1
```

comprobar que FastAPI responde (200):

```bash
curl.exe -i http://localhost:8000/health
```

comprobar que Spring Boot responde (200):

```bash
curl.exe -i http://localhost:8080/health
```

Abre el [chatbot](http://localhost:8000) para comparar respuestas o [Swagger de FastAPI](http://localhost:8000/docs) para probar el CRUD. PostgreSQL es accesible en `localhost:5432`; desde HDU-040 se publica como `5432:5432` en las interfaces del host para recibir conexiones de Minikube. FastAPI sigue en `localhost:8000` y Spring Boot en `localhost:8080`. La base guarda los datos en el volumen `pgdata`.

Python usa `public.patients` y Java usa `java.patients`, dentro de la misma base. Eso permite conservar y probar las filas de cada servicio por separado. En este equipo, Ana, Bruno y Carla Demo ya están cargados en ambas; los ids se generan de forma independiente. En un clon nuevo, usa los comandos de carga de la guía antes de probar persistencia.

## Contrato HTTP

Los cuerpos de POST y PUT llevan `name` (texto no vacío), `birth_date` (fecha real en formato `YYYY-MM-DD`) y `email` (dirección válida). PUT necesita los tres campos. Las respuestas con un paciente también incluyen su `id` entero, generado por PostgreSQL.

| Operación | Disponible en | Respuesta correcta | Error previsto |
|---|---|---|---|
| `GET /` | Python | 200, página del chatbot | — |
| `GET /health` | Python y Java | 200, `{"status":"ok"}` | — |
| `GET /metrics` | Python | 200, métricas en texto Prometheus | — |
| `GET /actuator/prometheus` | Java | 200, métricas en texto Prometheus | — |
| `POST /patients` | Python y Java | 201, paciente creado | 422 si la entrada no es válida |
| `GET /patients` | Python y Java | 200, lista ordenada por id | — |
| `GET /patients/{id}` | Python y Java | 200, paciente | 404 si no existe |
| `PUT /patients/{id}` | Python y Java | 200, paciente actualizado | 404 si no existe; 422 si la entrada no es válida |
| `DELETE /patients/{id}` | Python y Java | 204, sin cuerpo | 404 si no existe |
| `POST /chat` | Python | 200, `direct_answer`, `rag_answer`, `sources` | 422 entrada inválida; 404 paciente ausente; 503 servicio no disponible |

El 404 de ambas APIs usa `{"detail":"Paciente no encontrado"}`. Se comprobaron 14 entradas inválidas en POST y PUT: nombre vacío o numérico, fechas imposibles o con formato incorrecto, emails inválidos o sin dominio completo y campos ausentes. Cada API devolvió 28 respuestas 422 sin guardar cambios. El detalle interno de los errores 422 puede ser distinto entre frameworks; se comparan los códigos y el efecto en los datos, sin exigir mensajes idénticos.

## Probar cada operación

Esta secuencia usa Python en el puerto 8000. Hazla en la misma ventana de PowerShell: `$prueba.id` conserva el id recién creado. Así editas y borras solo tu registro de prueba. `curl.exe` muestra el código HTTP; `Invoke-RestMethod` muestra el JSON como un objeto de PowerShell.

crear y guardar el id del paciente temporal:

```powershell
$prueba = Invoke-RestMethod -Method Post -Uri http://localhost:8000/patients -ContentType 'application/json' -Body '{"name":"Prueba Guia","birth_date":"1995-05-05","email":"guia@example.com"}'
```

listar:

```bash
curl.exe -i http://localhost:8000/patients
```

consultar el creado:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/patients/$($prueba.id)"
```

editar sus tres campos:

```powershell
Invoke-RestMethod -Method Put -Uri "http://localhost:8000/patients/$($prueba.id)" -ContentType 'application/json' -Body '{"name":"Prueba Editada","birth_date":"1996-06-06","email":"editada@example.com"}'
```

borrar el creado (ojo, elimina ese registro; debe mostrar 204):

```powershell
(Invoke-WebRequest -UseBasicParsing -Method Delete -Uri "http://localhost:8000/patients/$($prueba.id)").StatusCode
```

consultar después del borrado (404):

```powershell
curl.exe -i "http://localhost:8000/patients/$($prueba.id)"
```

repetir el CRUD y los errores automáticamente, conservando los pacientes previos:

```powershell
Get-Content -Raw scripts/verificar_crud.py | docker compose exec -T python-api python - --base-url http://localhost:8000
```

comprobar que los datos Python sobreviven al reinicio:

```powershell
.\scripts\verificar_persistencia.ps1
```

comprobar lo mismo para Java:

```powershell
.\scripts\verificar_persistencia.ps1 -Servicio java-api
```

Cada prueba reinicia PostgreSQL y la API elegida, compara sus filas y confirma los cuatro campos de Ana Demo. Requiere que Ana siga con sus datos originales y no borra `pgdata`. Ojo: durante el reinicio se interrumpe brevemente el acceso a la base para ambas APIs. Más detalle en la [guía](GUIA.md#comprobar-persistencia).

listar los mismos pacientes ficticios en Java (200):

```bash
curl.exe -i http://localhost:8080/patients
```

consultar a Ana en Java (200; id 1 en la carga inicial):

```bash
curl.exe -i http://localhost:8080/patients/1
```

Los comandos para crear, editar y borrar un temporal Java están en la [guía](GUIA.md#pacientes-java). Usa `$pruebaJava.id` para tocar solo el registro que acabas de crear. La carga de Ana, Bruno y Carla ya se ejecutó; repetirla duplica los tres pacientes.

comprobar automáticamente todo el CRUD Java y limpiar su temporal:

```powershell
Get-Content -Raw scripts/verificar_crud.py | docker compose exec -T python-api python - --base-url http://java-api:8080
```

El nombre `java-api` funciona dentro de la red de Docker; desde Windows usas `localhost:8080`. Ejecuta ambos verificadores para repetir la comparación. El CRUD y las 56 respuestas 422 esperadas pasaron entre ambas APIs; quedaron intactas las filas previas. Resultados en [evidencias S02](evidencias/S02.md).

## Historias ficticias

leer las historias ficticias de Ana, Bruno y Carla:

```powershell
Get-Content -Raw datos/paciente-1.md, datos/paciente-2.md, datos/paciente-3.md
```

leer las cuatro preguntas con su respuesta esperada:

```powershell
Get-Content -Raw datos/preguntas.json
```

Cada historia identifica al paciente por su id Python y tiene Enfermedad, Tratamiento y Medicamento: nueve secciones en total. Tres preguntas se responden desde esos textos. La cirugía de Ana no está documentada, así que se espera `No hay información suficiente`.

## Preparar los vectores

Ollama 0.40.12 corre en Windows y Qdrant 1.20.0 en Docker. Desde Windows, sus direcciones son `http://127.0.0.1:11434` y `http://localhost:6333`; desde `python-api` son `http://host.docker.internal:11434` y `http://qdrant:6333`.

descargar el modelo si todavía no está en este equipo:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull nomic-embed-text
```

crear o comprobar la colección:

```bash
docker compose exec -T python-api python preparar_vectores.py
```

Resultado comprobado: `historias`, **768 componentes**, distancia **Cosine**. `EMBEDDING_MODEL=nomic-embed-text` está centralizado en Compose y lo lee `app/knowledge.py`; preparación, ingesta y búsqueda usan esa configuración. La colección se conserva en `qdrant_data`.

cargar o actualizar las nueve secciones:

```bash
docker compose exec -T python-api python ingestar.py
```

Se ejecutó dos veces: ambas terminaron con nueve puntos, tres por paciente, y payloads iguales a los Markdown. Los UUID estables evitan duplicados al repetirlo. Cada punto conserva `patient_id`, `source`, `section` y `text`.

Marco autorizó continuar aunque no se alcance el mínimo documental de RAM; las comprobaciones de embeddings e ingesta pasaron. Más comandos y ubicación de Ollama en la [guía](GUIA.md#embeddings-y-qdrant).

## Buscar en los documentos

recuperar la enfermedad de Ana:

```powershell
docker compose exec -T python-api python buscar.py 1 "¿Qué enfermedad tiene Ana Demo?"
```

comprobar qué ocurre con un dato ausente:

```powershell
docker compose exec -T python-api python buscar.py 1 "¿Cuál fue la última cirugía de Ana Demo?"
```

La búsqueda devuelve hasta dos fragmentos del paciente solicitado, con score, archivo, sección y texto. Las tres preguntas conocidas recuperaron su respuesta en el primer resultado. La cirugía de Ana devolvió fragmentos de Enfermedad y Tratamiento que no contienen esa información: similitud no equivale a respuesta. `buscar.py` devuelve documentos; la llamada directa al LLM se prueba por separado. Las cuatro consultas están en la [guía](GUIA.md#buscar-por-paciente).

comprobar los nueve payloads y las cuatro preguntas automáticamente:

```powershell
Get-Content -Raw scripts\verificar_recuperacion.py | docker compose exec -T python-api python
```

Pasó antes y después de reiniciar Qdrant: nueve puntos conservados, tres por paciente, tres respuestas presentes y cirugía ausente. Todos los resultados correspondían al paciente solicitado. El reinicio reproducible está en la [guía](GUIA.md#comprobar-recuperación).

## Comparar respuestas con y sin RAG

En el [chatbot](http://localhost:8000), elige **Ana Demo**, escribe `¿Qué enfermedad tiene Ana Demo?` y pulsa **Consultar**. Verás las columnas **Sin RAG** y **Con RAG**, junto con los archivos y secciones recuperados. El selector obtiene los pacientes de la API y ambas ramas reciben el mismo texto.

Mientras responde aparece **Cargando…** y se desactivan el botón, el selector y la pregunta. El resultado identifica qué paciente y texto se consultaron. Una pregunta vacía muestra `Escribe una pregunta` sin enviarla. Si aparece `LLM no disponible`, inicia Ollama y pulsa Consultar otra vez: la pregunta se conserva y no necesitas recargar la página. Ese reintento se comprobó con Ollama realmente detenido y luego reiniciado. Paso a paso en la [guía](GUIA.md#chatbot-en-el-navegador).

Las cuatro preguntas de `datos/preguntas.json` pasaron desde la página: Enfermedad Alfa, Tratamiento Beta, Medicamento Gamma y cirugía sin información suficiente. Se comprobó que el texto enviado y las respuestas/fuentes visibles coinciden con el JSON. La [guía](GUIA.md#comprobar-las-cuatro-preguntas-en-la-página) deja los casos y cómo repetir la prueba; las respuestas completas están en [S04-ui-019.json](evidencias/S04-ui-019.json). La explicación personal y la revisión de Rui siguen pendientes.

descargar el modelo si todavía no está disponible:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull llama3.2:3b
```

enviar una pregunta con un paciente existente:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/chat -ContentType 'application/json; charset=utf-8' -Body '{"patient_id":1,"question":"¿Qué enfermedad tiene Ana Demo?"}' | ConvertTo-Json -Depth 5
```

La respuesta tiene `direct_answer`, `rag_answer` y `sources`. La directa recibe solo la pregunta; RAG añade hasta dos fragmentos del paciente. Ambas conservan la misma pregunta, `CHAT_MODEL=llama3.2:3b`, temperatura 0, contexto 2048 y máximo 256 tokens de salida. El timeout es de 120 segundos por llamada al LLM; una petición comparativa hace dos llamadas y la recuperación.

En las pruebas, RAG respondió Enfermedad Alfa con la fuente `[paciente-1.md/Enfermedad]`; para cirugía de Ana respondió `No hay información suficiente.`. La rama directa dijo que no tenía datos, lo cual es válido. La respuesta y la cita se generan desde el contexto, sin respuestas fijas en el código.

repetir ambos casos y comprobar las fuentes:

```powershell
Get-Content -Raw scripts\verificar_chat.py | docker compose exec -T python-api python
```

Si aparece 503 `LLM no disponible`, ejecuta el script de inicio de Ollama y reintenta. Una conexión fallida a Qdrant devuelve 503 `Qdrant no disponible`; pregunta vacía y paciente inexistente responden 422 y 404 respectivamente. Los prompts, respuestas y parámetros reales están en [S04-rag.json](evidencias/S04-rag.json).

## RAG en cuatro pasos

LangGraph 1.2.18 ejecuta `retrieval → prompt → llamada_llm → respuesta` en `python-api/grafo.py`. El estado conserva pregunta, patient_id, request_id, fragmentos, prompt y respuesta. Reutiliza las funciones y el modelo existentes:

| Paso | Qué añade al estado |
|---|---|
| retrieval | Hasta dos fragmentos del paciente solicitado. |
| prompt | La pregunta y los fragmentos dentro del prompt RAG. |
| llamada_llm | La respuesta real del modelo, con el mismo request_id. |
| respuesta | Entrega esa respuesta sin modificarla ni llamar otra vez al modelo. |

La [prueba HDU-034](evidencias/s08/034-grafo.md) se ejecutó por consola: la pregunta exacta del dataset sobre Ana devolvió Enfermedad Alfa con su fuente. [Comandos para repetirla](GUIA.md#ejecutar-el-grafo). Esa HDU comprobó el grafo de forma independiente.

Desde **HDU-035**, el POST `/chat` invoca ese StateGraph para la rama RAG y conserva la respuesta directa y las dos columnas. Las dos preguntas de Ana pasaron en la página: enfermedad con Alfa y cita; cirugía sin información suficiente. Por petición se cotejaron cuatro nodos en orden, dos llamadas LLM y el HTTP 200, todos con el mismo request_id. [Casos, respuestas y capturas](evidencias/s08/casos-chatbot.md) y [cómo repetirlos](GUIA.md#comprobar-el-chatbot-con-el-grafo).

## Trazas del RAG en Phoenix

[Phoenix 20.26.1](http://localhost:6006) recibe las trazas del proyecto **genai** y conserva sus datos en `phoenix_data`. Python usa OpenTelemetry 1.45.1 y envía por lotes al endpoint interno `http://phoenix:6006/v1/traces`.

La [prueba HDU-036](evidencias/s08/phoenix.md) comprobó la primera raíz `rag`. Desde **HDU-037**, Phoenix muestra esa raíz y cuatro spans hijos con entrada, salida y duración por nodo. El mismo request_id enlaza los cinco spans y los siete logs del chatbot. Abre la [traza completa de Ana](http://localhost:6006/redirects/traces/e55201e7c50f71a9938bb739b9a66abd), selecciona `prompt` y revisa **Info** para ver los fragmentos y el prompt completo. [Prueba y capturas](evidencias/s08/037-nodos.md) · [Comandos de Phoenix](GUIA.md#trazas-en-phoenix).

## Métricas de FastAPI

ver contadores y duraciones HTTP:

```powershell
curl.exe -i http://localhost:8000/metrics
```

`http_requests_total` cuenta peticiones y `http_request_duration_seconds` agrupa duraciones en segundos. Las etiquetas son `method`, `route` y `status`; los pacientes comparten la ruta `/patients/{id}`, sin crear una serie por id. Los contadores viven en el proceso y se reinician con él. Las métricas incluyen también las consultas a `/metrics`.

repetir la comprobación de un 200 y un 404, sin modificar pacientes:

```powershell
Get-Content -Raw scripts/verificar_metricas.py | docker compose exec -T python-api python -
```

La prueba comprobó un incremento exacto de uno en el contador y en el count del histograma para cada status, con ruta normalizada. [Evidencia HDU-025](evidencias/s06/fastapi.md) y [detalle de uso](GUIA.md#métricas-fastapi).

## Prometheus y Grafana

Abre [Targets de Prometheus](http://localhost:9090/targets) y comprueba que `fastapi` y `springboot` estén **UP**. Prometheus 3.15.1 recoge métricas cada 15 segundos usando los nombres internos de Compose. Java expone contadores y buckets con Actuator/Micrometer; se comprobaron incrementos exactos de uno para GET 200 y 404.

repetir la comprobación de métricas Java:

```powershell
Get-Content -Raw scripts/verificar_metricas.py | docker compose exec -T python-api python - --service springboot
```

Entra a [Grafana 13.3.0](http://localhost:3000) con usuario `admin` y la clave `GRAFANA_ADMIN_PASSWORD` de tu `.env`. La [guía](GUIA.md#prometheus-y-grafana) muestra cómo verla localmente. La fuente Prometheus ya está configurada y su **Save & test** pasó. [Evidencia HDU-026](evidencias/s06/026.md).

El dashboard [APIs GenAI](http://localhost:3000/d/genai-apis/apis-genai) tiene una fila por API, con tráfico en peticiones/segundo, errores 4xx/5xx en porcentaje y latencia p95 en segundos. Usa una ventana de cinco minutos y calcula errores como `100 * $B / $A`. El p95 estima el tiempo bajo el que quedó el 95 % de las peticiones, a partir de los buckets del servidor. [Consultas de tráfico/errores](evidencias/s06/consultas.md) y [prueba de latencia](evidencias/s06/028-latencia.md).

La carga de HDU-028 hizo 20 GET válidos y 5 inexistentes por API en unos dos minutos: 50 respuestas correctas, sin modificar pacientes. Los seis paneles devolvieron datos numéricos; los últimos p95 observados fueron 0,004760 s en FastAPI y 0,009647 s en Java. Son resultados de ese ensayo, no una garantía de rendimiento. El [comando para repetirlo](GUIA.md#carga-y-latencia-p95) usa el Python disponible en este equipo.

Sin tráfico, el porcentaje puede quedar sin valor; no significa automáticamente 0 %. También cuentan health y las consultas a métricas. La configuración está en `observabilidad/` y los cambios del dashboard se leen cada 30 segundos. Los volúmenes `prometheus_data` y `grafana_data` conservan los datos de estos servicios.

La [revisión HDU-029](evidencias/s06/revision.md) repitió GET 200/404, confirmó el incremento exacto de uno por petición y comprobó los seis paneles con datos finitos. Incluye exportación, capturas y tres frases para repasar req/s, error % y p95. Puedes [repetir la revisión](GUIA.md#revisar-el-dashboard); la explicación personal de Marco y la revisión de Rui siguen pendientes.

## Logs por petición

Ambas APIs devuelven `X-Request-ID` y escriben un evento JSON con ese mismo `request_id`, fecha UTC, servicio, método, ruta, status y duración en milisegundos. Puedes enviar tu propio id válido; si falta o no es válido, generan un UUID. Las rutas se normalizan y los eventos HTTP no incluyen cuerpos ni parámetros de consulta.

La prueba [HDU-030](evidencias/s07/030-logs.md) relacionó cuatro respuestas 200/404 con sus cuatro logs y comprobó un 500 Python aislado. La [guía de logs](GUIA.md#logs) permite repetirlo y consultar ambos contenedores.

**Loki 3.7.9 y Alloy 1.21.2** llevan esos logs a Grafana. Alloy recoge solo las dos APIs de este proyecto; `service` identifica `fastapi` o `springboot`, mientras `request_id` se consulta dentro del JSON. Loki escucha en `localhost:3100`; la fuente **Loki** de Grafana usa la dirección interna `http://loki:3100` y su Save & test pasó. Se vieron dos eventos 200/404 por API en Explore con sus ids correctos. [Guía de consulta](GUIA.md#logs-en-grafana) y [evidencia HDU-031](evidencias/s07/loki-apis.md).

Las llamadas al LLM añaden eventos `llm`: rama `direct` o `rag`, modelo, prompt completo, respuesta, duración y estado. Comparten el id del POST `/chat`, conservando el mismo modelo y parámetros. La [prueba HDU-032](evidencias/s07/llm.md) mostró ambas ramas en Explore; RAG respondió Alfa con fuente y la directa pidió contexto. Como estos eventos sí contienen la pregunta y el contexto, sigue usando los datos ficticios de la práctica. [Cómo repetirlo](GUIA.md#logs-del-llm).

La [revisión HDU-033](evidencias/s07/revision.md) volvió a consultar los intervalos guardados: dos eventos HTTP por API y, para el chatbot, dos eventos LLM más el HTTP 200. **El request_id une la petición con sus llamadas al modelo**; el filtro por servicio separa las APIs. La guía explica [cómo seguir ese recorrido](GUIA.md#seguir-una-consulta-completa). La explicación personal y la revisión de Rui siguen pendientes.

## Preparar Minikube

La preparación HDU-039 se comprobó el **28/10/2026**; el 04/01 sigue siendo la fecha prevista del plan. El arranque del README, ambos health, Ana y la pregunta RAG pasaron: [arranque](evidencias/s09/039-arranque.txt), [APIs](evidencias/s09/039-apis.json) y [chat con cinco spans y siete logs](evidencias/s09/039-chat.json).

`scripts/instalar_gitops.ps1` dejó Minikube **1.39.0**, kubectl **1.36.6** y Helm **4.3.1** en `.local/bin`, comprobando los SHA-256 oficiales y las versiones. No cambia el PATH. [Herramientas verificadas](evidencias/s09/039-herramientas.json).

iniciar el perfil genai con 2 CPU, 3072 MiB y Kubernetes 1.36.6:
```powershell
.\.local\bin\minikube.exe start --profile=genai --driver=docker --cpus=2 --memory=3072 --kubernetes-version=v1.36.6 --keep-context --wait=all --wait-timeout=6m
```

`--keep-context` conserva el contexto activo; las consultas de esta práctica usan `kubectl --context=genai`. Se comprobaron **2 CPU y 3072 MiB reales**, el nodo `genai` **Ready** con Kubernetes 1.36.6 y la imagen **genai-fastapi:s09** cargada. [Resumen y evidencias HDU-039](evidencias/s09/039-resumen.md). La [guía](GUIA.md#preparar-minikube) deja los comandos para comprobar el nodo, construir y cargar la imagen. Esta HDU prepara la imagen; todavía no despliega FastAPI en Kubernetes.

## Chart de FastAPI y PostgreSQL

`deploy/helm/fastapi` describe un Deployment de una réplica y un Service ClusterIP, imagen `genai-fastapi:s09`, puerto 8000 y readiness `GET /health` cada cinco segundos tras una espera inicial de cinco segundos. El alcance Kubernetes es el **CRUD de FastAPI**; el chatbot con sus servicios RAG sigue disponible en [Compose, puerto 8000](http://localhost:8000).

En este equipo, `host.minikube.internal` resolvió a **192.168.65.254**. El chart usa esa IP para PostgreSQL, base `genai`, puerto 5432 y Secret `genai-postgres` en el namespace `genai`. El script de la [guía](GUIA.md#chart-y-conexión-a-postgres) crea o actualiza el Secret desde tu `.env` sin guardar credenciales en el chart. `helm lint` y `helm template` pasaron; un pod temporal ejecutó `SELECT 1` y devolvió 1, y luego se eliminó. Las cuatro filas Python y tres Java se conservaron al cambiar la publicación de PostgreSQL. [Evidencia HDU-040](evidencias/s09/040-helm.md). El chart queda preparado; su instalación es el siguiente paso.

## Ubicarse en el código

| Archivo | Para qué sirve |
|---|---|
| `compose.yml` | Arranca los servicios y conserva PostgreSQL en `pgdata`. |
| `python-api/app/main.py` | Endpoints y búsqueda que responde 404. |
| `python-api/app/schemas.py` | Valida lo que entra y define el JSON de salida. |
| `python-api/app/models.py` | Define la tabla `public.patients`. |
| `python-api/app/db.py` | Abre la conexión y entrega una sesión por petición. |
| `python-api/app/metrics.py` | Cuenta peticiones y duraciones por método, ruta normalizada y status. |
| `python-api/app/observability.py` | Conserva el request_id entre middleware y endpoint y escribe eventos JSON HTTP/LLM. |
| `python-api/app/tracing.py` | Configura OpenTelemetry y registra entradas/salidas y tiempos de cada nodo en Phoenix. |
| `java-api/pom.xml` | Dependencias y versión de Spring Boot; Maven construye el servicio. |
| `java-api/src/main/resources/application.properties` | Configura la conexión de Java usando las variables de Compose. |
| `java-api/src/main/resources/schema.sql` | Crea el esquema `java` si todavía no existe. |
| `java-api/src/main/java/com/conkord/genai/PatientController.java` | Recibe las peticiones de pacientes y usa el repositorio JPA. |
| `java-api/src/main/java/com/conkord/genai/PatientRequest.java` | Valida nombre, fecha y email recibidos por Java. |
| `java-api/src/main/java/com/conkord/genai/HttpLoggingFilter.java` | Devuelve X-Request-ID y registra los metadatos HTTP de Java. |
| `java-api/src/main/resources/logback-spring.xml` | Escribe los eventos HTTP Java como una línea JSON. |
| `datos/pacientes.json` | Los tres pacientes ficticios iniciales. |
| `datos/paciente-1.md` a `paciente-3.md` | Historias ficticias vinculadas a los ids de Python. |
| `datos/preguntas.json` | Cuatro preguntas y respuestas esperadas para probar recuperación. |
| `scripts/verificar_crud.py` | Prueba reproducible por HTTP; limpia su paciente temporal. |
| `scripts/verificar_persistencia.ps1` | Reinicia servicios y compara los pacientes antes/después. |
| `scripts/iniciar_ollama.ps1` | Inicia o reutiliza Ollama local en Windows. |
| `scripts/esperar_apis.ps1` | Espera health de ambas APIs con un plazo máximo de 90 segundos. |
| `python-api/app/knowledge.py` | Comparte la configuración y las llamadas HTTP a Ollama/Qdrant. |
| `python-api/preparar_vectores.py` | Comprueba la dimensión real y prepara la colección `historias`. |
| `python-api/ingestar.py` | Valida los Markdown e ingiere sus secciones sin duplicarlas. |
| `python-api/buscar.py` | Recupera hasta dos fragmentos filtrados por paciente. |
| `scripts/verificar_recuperacion.py` | Coteja los nueve payloads y las cuatro consultas conocidas. |
| `python-api/app/llm.py` | Llama al LLM con parámetros compartidos y registra cada rama, prompt y respuesta. |
| `python-api/rag.py` | Construye el prompt RAG con pregunta, contexto y regla de cita. |
| `python-api/grafo.py` | Ejecuta los cuatro nodos RAG y permite guardar el estado final desde consola. |
| `scripts/verificar_chat.py` | Comprueba las dos respuestas y fuentes para dato conocido y ausente. |
| `python-api/app/static/index.html` | Página del chatbot: selector, pregunta, dos respuestas, fuentes y reintento. |
| `scripts/verificar_chat_ui.cjs` | Prueba el formulario en Edge y compara las cuatro respuestas visibles con el JSON. |
| `scripts/verificar_metricas.py` | Compara métricas antes/después de un GET 200 y otro 404. |
| `observabilidad/prometheus.yml` | Recoge ambas APIs cada 15 segundos y les asigna la etiqueta service. |
| `observabilidad/grafana-datasources.yml` | Configura las fuentes Prometheus y Loki de Grafana. |
| `observabilidad/dashboard.json` | Define los paneles del dashboard APIs GenAI. |
| `observabilidad/grafana-dashboards.yml` | Carga el dashboard desde su archivo. |
| `scripts/generar_trafico.py` | Hace 50 GET en unos dos minutos y guarda horas, estados y tiempos de respuesta. |
| `scripts/verificar_dashboard.cjs` | Consulta los seis paneles en Grafana y guarda resultados y capturas. |
| `scripts/verificar_logs.py` | Coteja cuatro respuestas HTTP con un evento JSON por request_id. |
| `observabilidad/loki.yml` | Configura Loki con almacenamiento local persistente. |
| `observabilidad/alloy.alloy` | Recoge los logs de las dos APIs y los envía a Loki. |
| `scripts/verificar_loki.py` | Genera cuatro GET y encuentra sus eventos por servicio y request_id. |
| `scripts/capturar_loki.cjs` | Abre las consultas verificadas en Explore y guarda capturas y URLs. |
| `scripts/verificar_llm_logs.py` | Comprueba que las dos llamadas LLM coincidan con el POST y su respuesta en Loki. |
| `scripts/verificar_grafo_logs.py` | Relaciona los casos del navegador con cuatro nodos, dos llamadas LLM y su HTTP en Loki. |
| `scripts/capturar_phoenix.cjs` | Abre una traza guardada y comprueba que sus ids aparezcan antes de capturarla. |
| `scripts/verificar_traza.py` | Envía el caso de Ana y coteja cinco spans con sus entradas/salidas y siete logs. |
| `scripts/instalar_gitops.ps1` | Descarga y verifica las herramientas Windows x64 en .local/bin, sin cambiar el PATH. |
| `deploy/helm/fastapi/values.yaml` | Define imagen, réplica, conexión PostgreSQL y recursos del microservicio. |
| `deploy/helm/fastapi/templates/` | Plantillas del Deployment con readiness y del Service ClusterIP. |
| `scripts/crear_secret_postgres.ps1` | Crea namespace/Secret desde .env por stdin, sin imprimir credenciales. |

El recorrido Python es JSON → validación → endpoint → sesión SQLAlchemy → PostgreSQL → respuesta. En Java es JSON → `PatientRequest` → controlador → repositorio JPA → PostgreSQL → respuesta. El código y las pruebas no acreditan todavía la explicación de Marco ni la revisión de Rui; esos pendientes se registran aparte.
