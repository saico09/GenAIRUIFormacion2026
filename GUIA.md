# Guía rápida

Todo se corre desde la carpeta `codigo` (es el repo de Git), en **PowerShell 7**, probado con **7.6.5**. Docker Desktop tiene que estar abierto. La entrada rápida y el contrato HTTP están en [README.md](README.md).

Para recorrerlo todo usa [el guion final](evidencias/s10/guion.md); [la evaluación](evidencias/s10/evaluacion.md) separa resultados técnicos y revisión humana pendiente. El estado actual de Minikube tiene **dos réplicas**.

usa `curl.exe` para llamar al ejecutable sin depender de los alias de tu terminal.

entrar a la carpeta:
```bash
cd C:/Users/marco/Documents/CONKORD/GenAIRUIFormacion2026/codigo
```

## Primera vez (solo en un equipo nuevo)

ojo: tu `.env` ya existe. Este paso es solo para un clon nuevo del repo y no reemplaza un archivo existente. Completa los valores antes de levantar los servicios; no subas ese archivo a Git.

crear el .env solo si no existe (PowerShell; después pon usuario y clave):
```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Abre `.env` en tu editor y completa `POSTGRES_USER`, `POSTGRES_PASSWORD` y `GRAFANA_ADMIN_PASSWORD`. La última es la clave local que quieres usar para entrar como `admin` a Grafana; no dejes el valor vacío ni subas el archivo a Git. En este equipo ya está configurada.

## Levantar / bajar

levantar los contenedores (postgres, ambas apis, qdrant, prometheus, grafana, loki, alloy y phoenix), reconstruyendo si cambiaste código:
```bash
docker compose up -d --build
```

esperar las dos apis antes de consultarlas (plazo máximo de 90 segundos):
```powershell
.\scripts\esperar_apis.ps1
```

Compose puede mostrar Started antes de que la API responda. El script consulta health con intentos acotados y avisa si alguna no queda lista.

ver qué está corriendo:
```bash
docker compose ps
```

bajar los contenedores (se conservan los volúmenes; Ollama corre aparte en Windows):
```bash
docker compose down
```

bajar los contenedores y BORRAR los datos (ojo: elimina pacientes, vectores, historial Prometheus, datos Grafana, logs Loki, posiciones Alloy y trazas Phoenix):
```bash
docker compose down -v
```

## Postgres

ver si postgres acepta conexiones:
```bash
docker compose exec postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

entrar a la base con psql (sales con `\q`):
```bash
docker compose exec postgres psql -U genai -d genai
```

ver la tabla de pacientes directo en la base:
```bash
docker compose exec postgres psql -U genai -d genai -c "SELECT id, name, birth_date, email FROM public.patients;"
```

ver cómo quedó creada la tabla (columnas y tipos):
```bash
docker compose exec postgres psql -U genai -d genai -c "\d public.patients"
```

ver usuario y clave para DBeaver:
```bash
cat .env
```

conectar con DBeaver: Nueva conexión → PostgreSQL → Host `localhost`, Puerto `5432`, Base `genai`, usuario y clave los del `.env`. Si pide driver, dejar que lo descargue. Solo funciona con los contenedores arriba.

Desde HDU-040, Compose publica PostgreSQL como `5432:5432` para la conexión desde Minikube; el puerto queda en las interfaces del host, no limitado a 127.0.0.1. Conserva la autenticación y el volumen `pgdata`.

## python-api

probar que la api está viva (debe responder 200 y {"status":"ok"}):
```bash
curl.exe -i http://localhost:8000/health
```

documentación automática de FastAPI (ahí puedes probar cada endpoint con "Try it out"): abrir http://localhost:8000/docs en el navegador.

## java-api

levantar o reconstruir java-api y su dependencia postgres:
```bash
docker compose up -d --build --wait java-api
```

probar que java-api está viva (200 y {"status":"ok"}):
```bash
curl.exe -i http://localhost:8080/health
```

Java usa el mismo PostgreSQL, pero su tabla es `java.patients`; FastAPI mantiene `public.patients`. Cada API conserva sus filas por separado. Java ya permite crear, listar, consultar, editar y borrar pacientes.

## Pacientes Python

cargar los 3 pacientes de `datos/pacientes.json` (PowerShell; muestra 201 y el id de cada uno). Ojo: si lo corres de nuevo, se duplican:
```powershell
(Get-Content datos/pacientes.json -Raw | ConvertFrom-Json) | ForEach-Object { $r = Invoke-WebRequest -UseBasicParsing -Method Post -Uri http://localhost:8000/patients -ContentType 'application/json' -Body ($_ | ConvertTo-Json); "$($r.StatusCode) $($r.Content)" }
```

listar todos:
```bash
curl.exe -i http://localhost:8000/patients
```

crear un paciente ficticio temporal y guardar su id (sigue los próximos pasos en la misma ventana de PowerShell):
```powershell
$prueba = Invoke-RestMethod -Method Post -Uri http://localhost:8000/patients -ContentType 'application/json' -Body '{"name":"Prueba Guia","birth_date":"1995-05-05","email":"guia@example.com"}'
```

ver solo el paciente recién creado (200):
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/patients/$($prueba.id)"
```

editar los tres campos de ese paciente (200; PUT necesita el cuerpo completo):
```powershell
Invoke-RestMethod -Method Put -Uri "http://localhost:8000/patients/$($prueba.id)" -ContentType 'application/json' -Body '{"name":"Prueba Editada","birth_date":"1996-06-06","email":"editada@example.com"}'
```

borrar solo ese paciente de prueba (204 y cuerpo vacío; ojo, este registro sí se borra de la base):
```powershell
(Invoke-WebRequest -UseBasicParsing -Method Delete -Uri "http://localhost:8000/patients/$($prueba.id)").StatusCode
```

comprobar que el paciente borrado ya no existe (404):
```powershell
curl.exe -i "http://localhost:8000/patients/$($prueba.id)"
```

probar un id inexistente (404; comprobado con 999999):
```bash
curl.exe -i http://localhost:8000/patients/999999
```

probar que rechaza datos malos (422 y no guarda nada):
```powershell
try { Invoke-RestMethod -Method Post -Uri http://localhost:8000/patients -ContentType 'application/json' -Body '{"name":"Prueba Invalida","birth_date":"2026-02-30","email":"guia@example.com"}' } catch { $_.Exception.Response.StatusCode.value__; $_.ErrorDetails.Message }
```

## Pacientes Java

En este equipo, Ana, Bruno y Carla ya están cargados en Java. Los campos JSON son los mismos que en Python: `name`, `birth_date` y `email`; cada tabla genera sus propios ids, así que no dependas de que coincidan entre APIs.

cargar los tres ficticios solo si todavía no están (ojo: repetirlo duplica las filas):
```powershell
(Get-Content datos/pacientes.json -Raw | ConvertFrom-Json) | ForEach-Object { $r = Invoke-WebRequest -UseBasicParsing -Method Post -Uri http://localhost:8080/patients -ContentType 'application/json' -Body ($_ | ConvertTo-Json); "$($r.StatusCode) $($r.Content)" }
```

listar los pacientes de Java (200):
```bash
curl.exe -i http://localhost:8080/patients
```

consultar a Ana Demo en Java (200; el id 1 corresponde a la carga inicial comprobada):
```bash
curl.exe -i http://localhost:8080/patients/1
```

Un id que no existe devuelve 404. Si el nombre está vacío, la fecha no existe o el email no es válido, POST devuelve 422 y no crea una fila. La fecha usa `YYYY-MM-DD`, igual que en Python.

crear un temporal Java para probar edición y borrado (conserva esta ventana de PowerShell):
```powershell
$pruebaJava = Invoke-RestMethod -Method Post -Uri http://localhost:8080/patients -ContentType 'application/json' -Body '{"name":"Test Demo","birth_date":"1995-05-05","email":"test@example.com"}'
```

consultar el temporal Java (200):
```powershell
Invoke-RestMethod -Uri "http://localhost:8080/patients/$($pruebaJava.id)"
```

editar sus tres campos (200; PUT necesita todos):
```powershell
Invoke-RestMethod -Method Put -Uri "http://localhost:8080/patients/$($pruebaJava.id)" -ContentType 'application/json' -Body '{"name":"Test Editado","birth_date":"1996-06-06","email":"editado@example.com"}'
```

borrar solo el temporal Java (ojo, elimina ese registro; debe mostrar 204):
```powershell
(Invoke-WebRequest -UseBasicParsing -Method Delete -Uri "http://localhost:8080/patients/$($pruebaJava.id)").StatusCode
```

comprobar que ya no existe (404):
```powershell
curl.exe -i "http://localhost:8080/patients/$($pruebaJava.id)"
```

## Comprobar el CRUD

repetir la prueba completa usando el Python del contenedor (no necesitas instalar Python en Windows):
```powershell
Get-Content -Raw scripts/verificar_crud.py | docker compose exec -T python-api python - --base-url http://localhost:8000
```

repetir la misma prueba contra Java (el script corre dentro de Python y encuentra al otro contenedor por `java-api`):
```powershell
Get-Content -Raw scripts/verificar_crud.py | docker compose exec -T python-api python - --base-url http://java-api:8080
```

El script crea un paciente ficticio, lo consulta, cambia sus tres campos y lo borra. Comprueba 404 en GET/PUT/DELETE, 204 sin cuerpo y 14 entradas inválidas tanto en POST como en PUT: son 28 respuestas 422 por API. Incluye nombre vacío/numérico, fechas imposibles o con formato incorrecto, email inválido o sin dominio completo y campos ausentes. Al terminar verifica que los pacientes que había antes siguen iguales. Si falla, intenta limpiar únicamente el paciente que creó y muestra cualquier limpieza pendiente. No edites pacientes desde otra ventana durante la prueba.

Para comparar Python y Java, ejecuta los dos comandos de arriba. Se comparan los códigos HTTP, los campos devueltos y que los errores no cambien datos; el texto y la estructura interna de los errores 422 pueden ser distintos entre frameworks. Las [evidencias S02](evidencias/S02.md) guardan los resultados comprobados.

`schemas.py` revisa la entrada antes de llegar al endpoint; `main.py` usa la sesión de `db.py`, guarda el modelo de `models.py` y confirma el cambio con `commit()`. `find_patient()` resuelve la búsqueda compartida: si no existe el id, responde 404. No hace falta memorizarlo: sigue un POST y luego un PUT para ver el recorrido.

En Java, `PatientRequest` valida, `PatientController` recibe la petición y `PatientRepository` accede a PostgreSQL mediante JPA. `findPatient()` comparte el 404. En PUT, `@Transactional` mantiene juntos la búsqueda y el cambio: al confirmar la transacción, JPA guarda los tres campos modificados.

## Comprobar persistencia

reiniciar postgres y python-api y comprobar que los pacientes siguen iguales:
```powershell
.\scripts\verificar_persistencia.ps1
```

reiniciar postgres y java-api y comprobar lo mismo en Java:
```powershell
.\scripts\verificar_persistencia.ps1 -Servicio java-api
```

Ojo: durante el reinicio se interrumpe brevemente el acceso a los datos de ambas APIs porque comparten PostgreSQL. La prueba necesita que exista Ana Demo original en la API elegida; compara todas sus filas y los cuatro campos de Ana antes/después, sin mostrar datos de otros pacientes. No borra el volumen `pgdata`. Evita editar pacientes mientras corre.

`pgdata` conserva los datos aunque el contenedor se reinicie. En `db.py`, `pool_pre_ping=True` comprueba que la conexión siga viva antes de reutilizarla; así descarta conexiones viejas después de un reinicio de PostgreSQL.

En Java, JPA trabaja con la tabla `java.patients`; la tabla de Python sigue siendo `public.patients`. El reinicio Java conservó sus tres pacientes, y Ana siguió disponible también desde Python. La revisión con Rui y la explicación personal del recorrido del dato siguen pendientes.

## Historias ficticias

leer las tres historias usadas en la ingesta:
```powershell
Get-Content -Raw datos/paciente-1.md, datos/paciente-2.md, datos/paciente-3.md
```

leer las cuatro preguntas y sus respuestas esperadas:
```powershell
Get-Content -Raw datos/preguntas.json
```

Cada historia tiene `patient_id` y tres secciones: Enfermedad, Tratamiento y Medicamento. Son nueve secciones en total, vinculadas a Ana, Bruno y Carla por sus ids Python 1, 2 y 3. Los valores Alfa/Beta/Gamma son ficticios. La pregunta sobre la última cirugía de Ana no tiene respuesta en los documentos; se espera `No hay información suficiente`.

Los archivos ya se ingirieron en Qdrant: nueve secciones, tres por paciente. La rama RAG recupera hasta dos de esas secciones para responder con contexto. Marco autorizó continuar aunque no se alcance el mínimo documental de RAM; el avance se comprueba con el funcionamiento real.

## Embeddings y Qdrant

En este equipo Ollama 0.40.12 quedó instalado en `$env:LOCALAPPDATA\Programs\Ollama`, desde el [ZIP oficial para Windows](https://github.com/ollama/ollama/releases/tag/v0.40.12). No hace falta añadirlo al PATH. El script siguiente reutiliza un servidor activo o lo inicia en segundo plano; usa un modelo cargado y una petición a la vez.

iniciar Ollama en Windows:
```powershell
.\scripts\iniciar_ollama.ps1
```

descargar el modelo de embeddings (ya está descargado en este equipo):
```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull nomic-embed-text
```

ver los modelos disponibles:
```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

comprobar que Qdrant responde (200):
```bash
curl.exe -i http://localhost:6333/collections
```

preparar o comprobar la colección usando la dimensión real del modelo:
```bash
docker compose exec -T python-api python preparar_vectores.py
```

La salida comprobada es `model: nomic-embed-text`, `collection: historias`, `size: 768`, `distance: Cosine`. El script crea la colección solo si falta; si existe con otra dimensión o distancia, avisa y la conserva. Los vectores viven en `qdrant_data`.

Desde Windows, Ollama responde en `http://127.0.0.1:11434`; usamos esa dirección porque `localhost` dio problemas con IPv6. Desde `python-api`, Compose configura `OLLAMA_BASE_URL=http://host.docker.internal:11434` y `QDRANT_URL=http://qdrant:6333`. `EMBEDDING_MODEL=nomic-embed-text` se define una vez en Compose y lo lee `app/knowledge.py` para mantener el mismo modelo en preparación, ingesta y búsqueda.

Si Ollama no inicia, el script indica dónde quedaron los logs: `$env:LOCALAPPDATA\Ollama\genai`. Compose no inicia ni detiene Ollama, porque corre en Windows.

## Ingerir las historias

cargar o actualizar las nueve secciones en Qdrant:
```bash
docker compose exec -T python-api python ingestar.py
```

Puedes repetir el mismo comando: se ejecutó dos veces y ambas terminaron con `count: 9`, tres puntos por paciente y `payloads_match: true`. Cada punto guarda `patient_id`, `source`, `section` y `text`. El UUID depende del paciente y la sección, así que la repetición actualiza ese punto sin duplicarlo.

Compose monta `datos/` como `/datos` de solo lectura. El script valida los archivos y genera los vectores antes de guardarlos; después compara todos los ids y payloads con los Markdown. Si sobran puntos o algo no coincide, avisa y no borra la colección. Si cambias los ids de PostgreSQL, revisa primero `patient_id` en los documentos y preguntas.

## Buscar por paciente

buscar la enfermedad de Ana (id 1):
```powershell
docker compose exec -T python-api python buscar.py 1 "¿Qué enfermedad tiene Ana Demo?"
```

buscar el tratamiento de Bruno (id 2):
```powershell
docker compose exec -T python-api python buscar.py 2 "¿Qué tratamiento sigue Bruno Demo?"
```

buscar el medicamento de Carla (id 3):
```powershell
docker compose exec -T python-api python buscar.py 3 "¿Qué medicamento recibe Carla Demo?"
```

buscar un dato que no está en los documentos:
```powershell
docker compose exec -T python-api python buscar.py 1 "¿Cuál fue la última cirugía de Ana Demo?"
```

`buscar.py` recibe el id y la pregunta entre comillas. Usa el mismo modelo de embeddings, filtra por ese `patient_id` y devuelve hasta dos fragmentos con `score`, `source`, `section` y `text`. Las tres preguntas conocidas recuperaron primero la sección que contiene Alfa, Beta o Gamma, siempre del paciente correcto.

Ojo con la cirugía: devolvió Enfermedad y Tratamiento de Ana, pero ninguno contiene la respuesta. Un score de similitud sirve para ordenar fragmentos; no demuestra que el dato exista. Esta búsqueda todavía no genera respuestas de un LLM.

## Comprobar recuperación

comparar los nueve fragmentos y repetir las cuatro preguntas:
```powershell
Get-Content -Raw scripts\verificar_recuperacion.py | docker compose exec -T python-api python
```

reiniciar solo Qdrant para comprobar persistencia:
```bash
docker compose restart qdrant
```

esperar hasta que la colección vuelva a responder y después repetir el verificador de arriba:
```powershell
Invoke-RestMethod http://127.0.0.1:6333/collections/historias
```

Antes y después del reinicio se conservaron nueve puntos, tres por paciente, con todos los payloads iguales a los Markdown. Las tres respuestas conocidas aparecieron, la cirugía siguió ausente y los ocho resultados pertenecían al paciente correcto. No hizo falta volver a ingerir. La revisión de Rui y la explicación personal de Marco siguen pendientes.

## Chatbot en el navegador

Con los contenedores y Ollama encendidos:

1. Abre [el chatbot](http://localhost:8000).
2. Elige **Ana Demo** en el selector; los pacientes vienen de FastAPI.
3. Escribe `¿Qué enfermedad tiene Ana Demo?` y pulsa **Consultar**.
4. Espera mientras aparece **Cargando…**. El botón, el selector y la pregunta se bloquean hasta terminar.
5. Compara **Sin RAG** y **Con RAG**. En la prueba, RAG respondió Enfermedad Alfa y mostró `paciente-1.md / Enfermedad`; la directa indicó que no tenía información.

La pregunta queda escrita y el resultado identifica al paciente consultado. Si está vacía o tiene solo espacios, verás `Escribe una pregunta` y no se enviará nada.

si aparece `LLM no disponible`, volver a iniciar Ollama:
```powershell
.\scripts\iniciar_ollama.ps1
```

Después pulsa **Consultar** otra vez en la misma página, sin recargar. Se comprobó el error 503 con Ollama detenido y el reintento correcto tras iniciarlo; el botón vuelve a habilitarse tanto en éxito como en error. Las capturas y resultados están en [S04](evidencias/S04.md).

## Comprobar las cuatro preguntas en la página

Elige el paciente de cada fila, pega la pregunta tal cual y pulsa Consultar. Estos cuatro casos ya pasaron desde el formulario:

| Paciente | Pregunta | Respuesta esperada con RAG |
|---|---|---|
| Ana Demo | ¿Qué enfermedad tiene Ana Demo? | Enfermedad Alfa; fuente Enfermedad de `paciente-1.md` |
| Bruno Demo | ¿Qué tratamiento sigue Bruno Demo? | Tratamiento Beta; fuente Tratamiento de `paciente-2.md` |
| Carla Demo | ¿Qué medicamento recibe Carla Demo? | Medicamento Gamma; fuente Medicamento de `paciente-3.md` |
| Ana Demo | ¿Cuál fue la última cirugía de Ana Demo? | No hay información suficiente |

La rama sin RAG reconoció falta de datos en los cuatro casos. En cirugía, las fuentes recuperadas no contienen una cirugía: aparecer en la lista no convierte un texto en evidencia de esa respuesta. Se mantienen la misma pregunta, modelo y parámetros en ambas ramas.

Para repetirlo automáticamente en este equipo se usó el Node/Playwright disponible en Codex y Edge. Estas rutas son locales; no son dependencias de la app.

indicar dónde está Playwright en este equipo:
```powershell
$env:NODE_PATH = 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
```

ejecutar las cuatro preguntas desde Edge (guarda resultados y capturas en `evidencias/`):
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts\verificar_chat_ui.cjs --dataset
```

El verificador comprueba los cuatro POST exactos, 200, respuestas y fuentes visibles iguales al JSON, paciente correcto y bloqueo/restauración de los campos. Las salidas completas están en [S04-ui-019.json](evidencias/S04-ui-019.json). Las frases de apoyo para repasar RAG están en [S04](evidencias/S04.md); la explicación de Marco y la revisión de Rui siguen pendientes.

## Comparar respuestas con y sin contexto

descargar el modelo de chat (ya está descargado en este equipo):
```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull llama3.2:3b
```

comprobar el modelo directamente:
```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" run llama3.2:3b "Responde hola"
```

preguntar desde FastAPI y recibir las dos respuestas:
```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/chat -ContentType 'application/json; charset=utf-8' -Body '{"patient_id":1,"question":"¿Qué enfermedad tiene Ana Demo?"}' | ConvertTo-Json -Depth 5
```

Devuelve 200 con `direct_answer`, `rag_answer` y `sources`. La rama directa recibe solo la pregunta; la rama RAG recibe la misma pregunta y hasta dos fragmentos del paciente elegido. Ambas usan el mismo modelo y temperatura. `patient_id` debe existir y `question` conserva el texto enviado. Una pregunta vacía responde 422; un paciente inexistente, 404.

En la prueba de Ana, la directa reconoció que no tenía información y la respuesta RAG devolvió Enfermedad Alfa con `[paciente-1.md/Enfermedad]`. Para la cirugía, RAG dijo `No hay información suficiente.`. Las fuentes de esa consulta son textos recuperados; no prueban que haya ocurrido una cirugía.

repetir las dos preguntas y comprobar respuestas, fuentes, prompts y parámetros:
```powershell
Get-Content -Raw scripts\verificar_chat.py | docker compose exec -T python-api python
```

`rag.py` arma el contexto y pide una cita literal del archivo/sección; la respuesta viene del modelo. `app/llm.py` centraliza `CHAT_MODEL=llama3.2:3b`, temperatura 0, contexto 2048, salida máxima de 256 tokens y timeout de 120 segundos por llamada al LLM. Cada petición comparativa hace dos llamadas y la recuperación, así que puede tardar más que la antigua respuesta directa.

Si Ollama no está disponible, responde 503 con `LLM no disponible`; inicia de nuevo con `scripts/iniciar_ollama.ps1` y reintenta. Una conexión inaccesible a Qdrant devuelve 503 con `Qdrant no disponible`: ese caso se comprobó con una API de prueba y una URL inaccesible, sin detener el servicio real.

## Ejecutar el grafo

Con los servicios y Ollama encendidos, esta prueba ejecuta los cuatro nodos desde consola. Usa la primera pregunta del dataset y guarda el estado completo: pregunta, paciente, id de petición, fragmentos, prompt y respuesta.

tomar el primer caso del dataset sin cambiar el texto:
```powershell
$caso = (Get-Content datos/preguntas.json -Raw | ConvertFrom-Json)[0]
```

generar un id para esta ejecución:
```powershell
$requestId = 'hdu034-' + [guid]::NewGuid().ToString('N')
```

ejecutar retrieval, prompt, llamada_llm y respuesta:
```powershell
docker compose exec -T python-api python grafo.py $caso.patient_id $caso.question --request-id $requestId --output /tmp/grafo.json
```

copiar el estado final a la carpeta de evidencias:
```powershell
docker compose cp python-api:/tmp/grafo.json evidencias/s08/grafo.json
```

Ojo: el último comando reemplaza `grafo.json`. La prueba devolvió Alfa con `[paciente-1.md/Enfermedad]`, dos fragmentos de Ana y el mismo request_id en el estado y el evento LLM. El nodo respuesta entrega el texto obtenido; no hace una segunda llamada. [Resultado y build comprobados](evidencias/s08/034-grafo.md).

LangGraph 1.2.18 funciona aquí con Python 3.15.2. Docker compila las dependencias que lo necesitan en una etapa separada; no hace falta instalar un compilador en Windows. La comprobación de HDU-034 fue por consola; desde HDU-035 el mismo grafo también responde en el endpoint.

## Comprobar el chatbot con el grafo

Abre [el chatbot](http://localhost:8000), elige Ana y prueba las preguntas exactas `¿Qué enfermedad tiene Ana Demo?` y `¿Cuál fue la última cirugía de Ana Demo?`. Pasaron las dos: RAG devolvió Alfa con fuente y falta de información para cirugía; la directa reconoció que no tenía datos. Las fuentes de cirugía son fragmentos recuperados de Ana, no evidencia de una operación.

Para repetir la prueba de navegador y cotejar sus logs, usa estos comandos en la misma terminal. Ojo: con el prefijo `035` se reemplazan los JSON y capturas de esa prueba; si lo cambias, cambia también los nombres de entrada y salida del último comando.

indicar dónde está Playwright en este equipo:
```powershell
$env:NODE_PATH = 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
```

guardar la prueba en la carpeta del grafo:
```powershell
$env:EVIDENCE_DIR = 'evidencias/s08'
```

identificar los resultados y las capturas:
```powershell
$env:EVIDENCE_PREFIX = '035'
```

probar enfermedad y cirugía desde la página:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts/verificar_chat_ui.cjs --demo
```

cotejar enseguida esos dos casos con los logs recientes de Loki:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_grafo_logs.py evidencias/s08/035-resultados.json --output evidencias/s08/035-correlacion.json
```

El segundo verificador consulta la última hora y exige cuatro eventos `rag_node` en orden, dos eventos `llm` con el mismo modelo y un HTTP 200. Compara la pregunta, las respuestas y las fuentes con el JSON del navegador; todos conservan su request_id. [Resultados y capturas inspeccionadas](evidencias/s08/casos-chatbot.md).

## Trazas en Phoenix

Abre [Phoenix](http://localhost:6006), entra al proyecto **genai** y selecciona una traza. Para ver la comprobación guardada, abre [esta traza de Ana](http://localhost:6006/redirects/traces/b257ce77561364693451e5a2324687ed) y la pestaña **Attributes**. Su request_id es `hdu036-a91935fe126a42a6b9530146db9ad37e`; coincide con los logs HTTP y LLM de Loki.

levantar solo Phoenix si todavía no está activo:
```powershell
docker compose up -d --no-deps phoenix
```

consultar por API los spans de la traza comprobada:
```powershell
Invoke-RestMethod 'http://localhost:6006/v1/projects/genai/spans?trace_id=b257ce77561364693451e5a2324687ed&limit=100'
```

En HDU-036 devolvió un único span `rag`, sin padre (`parent_id=null`), estado `OK` y duración positiva. Una traza nueva puede tardar unos segundos en aparecer porque el envío usa lotes; no hace falta repetir la pregunta inmediatamente. Las trazas quedan en el volumen `phoenix_data`.

La app conserva el proveedor global OpenTelemetry y lo cierra al apagar la API. Se desactivaron los spans automáticos HTTP/operación de FastAPI para que `rag` sea la raíz. Los primeros ensayos se conservan como históricos; usa el enlace de arriba para ver la prueba final. [Captura, correlación y configuración](evidencias/s08/phoenix.md).

Desde HDU-037, abre [la traza con los cuatro nodos](http://localhost:6006/redirects/traces/e55201e7c50f71a9938bb739b9a66abd). Bajo `rag` aparecen `retrieval`, `prompt`, `llamada_llm` y `respuesta`. Selecciona cada nodo y abre **Info** para ver su entrada y salida; **Attributes** conserva request_id y, en llamada_llm, modelo y parámetros.

enviar una pregunta nueva de Ana y comprobar los cinco spans y siete logs:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_traza.py --prefix hdu037 --output evidencias/s08/037-traza.json
```

El verificador imprime la URL de la nueva traza y compara la cadena de valores: los fragmentos de retrieval entran a prompt, ese prompt entra al LLM y su respuesta llega intacta al último nodo. También comprueba padre, orden, tiempos positivos y coincidencia con Loki. Ojo: reemplaza `037-traza.json`; cambia `--output` para conservar otra ejecución.

Los parámetros del span LLM y de la petición a Ollama salen del mismo `MODEL_OPTIONS`. En la prueba, prompt y respuesta tardaron 0,334 y 0,138 ms: Phoenix puede redondearlos a **0 ms** en pantalla, mientras el JSON conserva su duración positiva. [Entradas, salidas, tiempos y capturas inspeccionadas](evidencias/s08/037-nodos.md).

## Retomar después del receso

El receso previsto es **21/12/2026–01/01/2027**, sin tareas ni recuperación automática de pendientes. El **04/01/2027**, empieza por [Arrancar en el README](README.md#arrancar): Compose, espera de las APIs, Ollama y ambos health. Son pasos de reanudación; no incluyen repetir la parada de Qdrant rechazada anteriormente.

consultar a Ana después del arranque (200):
```powershell
curl.exe -i http://localhost:8000/patients/1
```

Después repite [la prueba de trazas](#trazas-en-phoenix): envía la pregunta de Ana y comprueba Alfa con fuente, cinco spans y siete logs. Revisa también Targets de Prometheus, el dashboard y Explore con los enlaces de esta guía. Si algo no está listo, registra el resultado antes de continuar con HDU-039; no des por hecha una comprobación anterior.

El [control HDU-038](evidencias/s08/control.md) guarda el estado y los pendientes. En esa prueba, POST `/chat` 200 aumentó en uno; el p95 del dashboard agrupa tráfico y no mide esa pregunta concreta. La explicación de Marco y la revisión con Rui siguen pendientes.

## Métricas FastAPI

ver las métricas HTTP (200; es texto Prometheus, no JSON):
```powershell
curl.exe -i http://localhost:8000/metrics
```

- `http_requests_total`: cuántas peticiones lleva el proceso.
- `http_request_duration_seconds_count` y `_sum`: cuántas duraciones midió y cuántos segundos suman.
- `http_request_duration_seconds_bucket`: cuántas peticiones quedaron dentro de cada límite de duración.

Cada serie distingue método, ruta y status. Para los pacientes se usa `/patients/{id}`; las rutas desconocidas se agrupan como `unmatched`. Así los ids concretos no generan series nuevas. Los contadores parten de nuevo si reinicias Python; consultar `/metrics` también cuenta como una petición.

comprobar que un GET de Ana y uno inexistente suman exactamente una petición cada uno:
```powershell
Get-Content -Raw scripts/verificar_metricas.py | docker compose exec -T python-api python -
```

La prueba pasó con 200 y 404, tanto en el contador como en el count del histograma; no modifica pacientes. Las duraciones miden hasta construir la respuesta. Resultado guardado en [s06/fastapi.md](evidencias/s06/fastapi.md).

## Prometheus y Grafana

1. Abre [Targets de Prometheus](http://localhost:9090/targets). `fastapi` y `springboot` deben aparecer **UP**.
2. Abre [Grafana](http://localhost:3000) y entra con usuario **admin**. La clave es el valor de `GRAFANA_ADMIN_PASSWORD` en tu `.env`.
3. Abre la fuente **Prometheus** y pulsa **Save & test**. Ya se comprobó el mensaje `Successfully queried the Prometheus API.`

consultar tu clave solo en la terminal local (no pegar el resultado en capturas ni evidencias):
```powershell
Get-Content .env | Select-String '^GRAFANA_ADMIN_PASSWORD='
```

La fuente se configura desde `observabilidad/grafana-datasources.yml` y usa `http://prometheus:9090`. Prometheus consulta `python-api:8000/metrics` y `java-api:8080/actuator/prometheus` cada 15 segundos. Dentro de Docker se usan esos nombres; `localhost` apuntaría al propio contenedor.

comprobar de nuevo las métricas Java con GET 200/404, sin modificar pacientes:
```powershell
Get-Content -Raw scripts/verificar_metricas.py | docker compose exec -T python-api python - --service springboot
```

validar el archivo de recolección:
```powershell
docker compose exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
```

Java usa `http_server_requests_seconds_count` y `_bucket`, con `uri="/patients/{id}"`; Prometheus añade `service="springboot"`. Para Python añade `service="fastapi"`. Al repetir los verificadores, evita otras peticiones a esos dos ids mientras se comparan los incrementos exactos. [Pruebas de conexión y métricas](evidencias/s06/026.md).

## Dashboard de las APIs

Abre [APIs GenAI](http://localhost:3000/d/genai-apis/apis-genai). Tiene dos filas, FastAPI y Spring Boot; cada una muestra tráfico en peticiones/segundo, errores 4xx/5xx en porcentaje y latencia p95 en segundos.

Las tasas usan los últimos cinco minutos. El panel de errores divide B (tasa de 4xx/5xx) por A (tasa total) mediante `100 * $B / $A`; ambas consultas están ocultas y se muestra el porcentaje. Si no existen series de errores, B toma `0 * tasa_total`: con tráfico positivo muestra 0 %, y sin métricas totales conserva No data. [Comprobación HDU-044](evidencias/s10/044-validacion-error-cero.json). El rango visible inicial es de quince minutos.

Ojo: también cuentan las peticiones de health y las consultas a métricas. Un GET correcto y uno 404 no implican exactamente 50 % en esa ventana. Sin tráfico puede no haber un porcentaje definido; no equivale a 0 %. Los cuatro paneles se comprobaron con datos numéricos en [HDU-027](evidencias/s06/consultas.md).

El dashboard vive en `observabilidad/dashboard.json`; Grafana lee sus cambios cada 30 segundos mediante `grafana-dashboards.yml`. Mantén los cambios en ese archivo para que queden en Git. Los datos persistentes de Grafana y Prometheus están en sus volúmenes.

## Carga y latencia p95

generar 20 GET válidos y 5 inexistentes por API en unos dos minutos, sin modificar pacientes:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\generar_trafico.py --output evidencias/s06/nueva-carga.json
```

Esa es la ruta Python probada en este equipo; `python` a secas no funciona aquí. El archivo de salida guarda cada petición, status, hora y duración. Cambia `nueva-carga.json` si quieres conservar una ejecución manual anterior.

Al terminar, espera al menos dos scrapes de 15 segundos y abre el dashboard en el intervalo que contiene la carga. Se comprobaron las 50 respuestas y los seis paneles con valores numéricos. [Resultados y capturas](evidencias/s06/028-latencia.md), [dashboard exportado](evidencias/s06/dashboard.json).

El **p95** estima el umbral bajo el que quedó el 95 % de las duraciones del servidor en cinco minutos; no es un promedio ni el tiempo de red del script. Se obtiene con `histogram_quantile(0.95, ...)` sobre los buckets. Grafana usa segundos y puede mostrar automáticamente milisegundos para valores pequeños. Los valores observados pertenecen a esta carga local; las peticiones de health y métricas también entran en el intervalo.

## Revisar el dashboard

Repite los verificadores de métricas Python y Java de arriba para comprobar que cada GET 200/404 suma uno; no modifican pacientes. Después espera dos scrapes de 15 segundos y abre [APIs GenAI](http://localhost:3000/d/genai-apis/apis-genai). La [revisión HDU-029](evidencias/s06/revision.md) comprobó los seis paneles y deja tres frases de apoyo sobre req/s, error % y p95. La explicación de Marco y la revisión de Rui siguen pendientes.

Para volver a consultar y capturar los paneles en este equipo, usa el Node/Playwright de Codex. El verificador lee la clave de `.env` sin imprimirla.

indicar dónde está Playwright:
```powershell
$env:NODE_PATH = 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
```

guardar los resultados en la carpeta de métricas:
```powershell
$env:EVIDENCE_DIR = 'evidencias/s06'
```

usar la fecha y hora como prefijo para conservar los ensayos anteriores:
```powershell
$env:EVIDENCE_PREFIX = Get-Date -Format 'yyyyMMdd-HHmmss'
```

consultar los seis paneles y guardar las capturas:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts/verificar_dashboard.cjs
```

El verificador fija un intervalo de quince minutos al empezar y lo reutiliza en la URL y en las consultas. Así el enlace guardado vuelve al intervalo de la captura. Cada nueva ejecución elige su propio intervalo; sin tráfico suficiente, un porcentaje o percentil puede quedar sin valor definido.

## Recorrer la demo de etapa 1

Abre el [guion S05](evidencias/S05-guion.md) y sigue los seis pasos: arranque, CRUD Python, CRUD Java, persistencia, búsqueda y chatbot. Cada paso enlaza el código, el resultado esperado y una evidencia real. Los CRUD usan un Test Demo propio y conservan los pacientes del RAG.

El arranque sobre el entorno existente y la repetición de ambos CRUD y cuatro preguntas pasaron en HDU-020/021. El ciclo completo desde detenido sigue **NO EJECUTADO**: la revisión automática rechazó detener Qdrant. El guion no repite esa parada; los reinicios de PostgreSQL y las APIs conservan sus volúmenes. [Pendientes concretos](evidencias/S05-pendientes.md).

La prueba UI admite `--demo` para solo enfermedad y cirugía de Ana, y `EVIDENCE_DIR` / `EVIDENCE_PREFIX` para guardar cada ensayo sin sobrescribir S04. Los comandos completos están al final del guion.

El [ensayo HDU-023](evidencias/S05-ensayo.md) repitió todos los pasos permitidos y añadió `esperar_apis.ps1` tras detectar una consulta demasiado temprana. Pasaron CRUD, persistencia, búsqueda y las cuatro preguntas. La [preparación HDU-024](evidencias/S05-validacion.md) volvió a comprobar health, Ana y las dos consultas de demo. Las frases del ensayo sirven para repasar; la explicación propia de Marco, la sesión y la valoración de Rui siguen pendientes.

## Postman

importar cada curl: en Postman, Import → Raw text → pegar el curl → Continue → Import. (También sirven en Git Bash, no en PowerShell.)

health:
```bash
curl --location 'http://localhost:8000/health'
```

listar pacientes:
```bash
curl --location 'http://localhost:8000/patients'
```

ver uno por id:
```bash
curl --location 'http://localhost:8000/patients/1'
```

crear paciente (queda guardado, cambia los datos para no duplicar):
```bash
curl --location 'http://localhost:8000/patients' --header 'Content-Type: application/json' --data-raw '{"name":"Nombre Demo","birth_date":"1995-05-05","email":"nombre@example.com"}'
```

crear con fecha inválida (debe dar 422 y no guardar nada):
```bash
curl --location 'http://localhost:8000/patients' --header 'Content-Type: application/json' --data-raw '{"name":"X","birth_date":"2026-02-30","email":"x@example.com"}'
```

## Logs

Cada petición deja un JSON con `timestamp`, `service`, `event`, `request_id`, `method`, `route`, `status` y `duration_ms`. `service` distingue `fastapi` y `springboot`; el header `X-Request-ID` de la respuesta permite localizar su evento.

Si envías ese header, se conserva cuando tiene entre 1 y 128 caracteres de `A-Z`, `a-z`, dígitos, `.`, `_`, `:` o `-`. Si falta o no cumple, se genera un UUID. Los eventos HTTP no guardan cuerpos, emails ni queries; los pacientes usan la ruta `/patients/{id}`. Los mensajes de arranque conservan el formato de cada runtime.

ver los eventos recientes de ambas apis sin el prefijo de Compose:
```powershell
docker compose logs --no-log-prefix --since 2m python-api java-api
```

comprobar GET 200/404 y su request_id en ambos servicios:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_logs.py
```

La prueba usa Ana y un id inexistente, conserva los pacientes y exige exactamente un evento por respuesta. Ojo: vuelve a generar `evidencias/s07/logs-apis.txt`. Los resultados y la comprobación aislada de error 500 están en [HDU-030](evidencias/s07/030-logs.md).

ver logs de la api en vivo (sales con Ctrl+C):
```bash
docker compose logs -f python-api
```

ver logs de postgres:
```bash
docker compose logs postgres
```

ver logs de java-api:
```bash
docker compose logs java-api
```

## Logs en Grafana

Alloy recoge solo `python-api` y `java-api` de este proyecto y envía sus líneas a Loki. En Grafana, la fuente **Loki** usa `http://loki:3100`; desde Windows el puerto es `localhost:3100`. Los volúmenes `loki_data` y `alloy_data` conservan logs y posiciones de lectura.

1. Entra a [Grafana](http://localhost:3000) con tu usuario y clave local.
2. Abre la fuente **Loki** y pulsa **Save & test**. La conexión ya se comprobó.
3. En **Explore**, elige **Loki** y el modo **Code** para pegar una consulta LogQL.
4. Usa el campo `query` y el intervalo `start_utc` / `end_utc` del JSON generado por la prueba siguiente. Cada consulta busca los dos eventos de un servicio por sus ids únicos.

generar cuatro GET y comprobar sus logs en Loki, sin modificar pacientes:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_loki.py --output evidencias/s07/loki-local.json
```

El verificador espera hasta 60 segundos a que lleguen los logs y guarda consultas, intervalos y eventos. Ojo: repetir ese nombre reemplaza `loki-local.json`; cambia el nombre para conservar una prueba manual anterior. Loki puede necesitar unos segundos para quedar listo al arrancar.

`service` permite separar FastAPI de Spring Boot. `| json` extrae los campos al consultar; `request_id` permanece dentro del JSON y no crea una etiqueta almacenada por petición. Se comprobaron cuatro eventos y las dos consultas en Explore: dos líneas por API, con 200/404 e ids correctos. [Resultados, URLs y capturas](evidencias/s07/loki-apis.md).

validar la configuración de Alloy sin reiniciarlo:
```powershell
docker compose exec -T alloy /bin/alloy validate /etc/alloy/config.alloy
```

validar la configuración de Loki sin reiniciarlo:
```powershell
docker compose exec -T loki /usr/bin/loki '-verify-config=true' '-config.file=/etc/loki/config.yml'
```

## Logs del LLM

Con Ollama, la API y Loki encendidos, cada comparación deja dos eventos `llm`, uno `direct` y otro `rag`, y un evento `http` del POST `/chat`. Desde HDU-035 también deja cuatro eventos `rag_node` para seguir el grafo. Comparten el request_id, incluso al pasar del middleware al hilo que ejecuta el endpoint.

preguntar por Ana y cotejar las dos llamadas LLM con la respuesta y los logs:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_llm_logs.py
```

Usa `¿Cuál es el diagnóstico de Ana?`, comprueba Alfa con fuente en RAG y compara los prompts, respuestas y duraciones. Ojo: regenera `evidencias/s07/032-llm.json`; ese archivo incluye la consulta LogQL y su intervalo para pegar en Explore, como en el apartado anterior.

`event="llm"` muestra modelo, rama, prompt completo, respuesta, `duration_ms` y `status`. El estado `ok` indica una respuesta válida; el código registra `error` y respuesta nula cuando falla la llamada. El evento HTTP conserva el estado HTTP numérico. El modelo y los parámetros son los mismos en ambas ramas; RAG añade el contexto recuperado.

Estos logs sí guardan el texto de la pregunta y los fragmentos usados, así que usa los datos ficticios de la práctica. La [evidencia HDU-032](evidencias/s07/llm.md) contiene las dos líneas vistas en Grafana, su consulta y captura. Los tiempos son de esa ejecución local, no un objetivo de rendimiento.

## Seguir una consulta completa

En Explore, conserva el filtro por `service` y `request_id`, pero quita `event="llm"` para ver también el evento HTTP. Esta consulta comprobada devuelve tres líneas: direct, rag y el POST `/chat` con status 200.

```logql
{service="fastapi"} | json | request_id="hdu032-b1f2ddff60e54e5cb1cb301cf59a9d76"
```

Usa el intervalo **28/10/2026 18:05:39.283233–18:07:53.514385 UTC**; la URL guardada en [033-explore.json](evidencias/s07/033-explore.json) ya lo incorpora. Para otra petición, toma su id y el intervalo de la evidencia nueva. Una ventana que no cubre la petición puede mostrar cero líneas aunque el evento exista.

La [revisión HDU-033](evidencias/s07/revision.md) también recuperó dos eventos 200/404 de cada API usando las consultas guardadas de HDU-031. Frase para repasarlo: **el request_id une la respuesta HTTP con los logs de sus llamadas al modelo; service distingue qué API los emitió**. Es apoyo para explicarlo, no una explicación personal ya realizada ni revisión de Rui recibida.

## Preparar Minikube

Docker Desktop debe estar disponible. Las herramientas de esta práctica quedan en `.local/bin`, dentro del repo e ignoradas por Git. El instalador verifica las descargas y reutiliza los archivos correctos; no cambia el PATH ni inicia el clúster.

preparar Minikube 1.39.0, kubectl 1.36.6 y Helm 4.3.1 para Windows x64:
```powershell
.\scripts\instalar_gitops.ps1
```

iniciar el perfil genai, conservando el contexto activo de Kubernetes:
```powershell
.\.local\bin\minikube.exe start --profile=genai --driver=docker --cpus=2 --memory=3072 --kubernetes-version=v1.36.6 --keep-context --wait=all --wait-timeout=6m
```

Se asignaron **2 CPU y 3072 MiB** a Minikube, comprobados en su contenedor. La primera ejecución descarga imágenes. `--keep-context` evita cambiar tu contexto activo; por eso las consultas de esta práctica llevan `--context=genai`. Marco autorizó continuar pese a la RAM libre baja y la prueba pasó; los [recursos observados](evidencias/s09/039-recursos.json) quedan registrados.

esperar a que el nodo genai esté Ready:
```powershell
.\.local\bin\kubectl.exe --context=genai wait --for=condition=Ready node/genai --timeout=90s
```

ver el nodo y su versión:
```powershell
.\.local\bin\kubectl.exe --context=genai get nodes -o wide
```

construir FastAPI con la etiqueta de esta etapa:
```powershell
docker build --tag genai-fastapi:s09 --progress=plain ./python-api
```

cargar la imagen en el perfil genai:
```powershell
.\.local\bin\minikube.exe --profile=genai image load genai-fastapi:s09
```

comprobar que la imagen aparece dentro de Minikube:
```powershell
.\.local\bin\minikube.exe --profile=genai image ls
```

La prueba mostró `genai` Ready con v1.36.6 y `docker.io/library/genai-fastapi:s09` en la lista. El build y la carga terminaron correctamente. [Resultados, hash de imagen y recursos](evidencias/s09/039-resumen.md). Cargar la imagen la deja disponible para Kubernetes; el despliegue del microservicio corresponde a los pasos siguientes.

## Chart y conexión a Postgres

El chart `deploy/helm/fastapi` prepara el CRUD de FastAPI en namespace `genai`. Lleva dos réplicas, imagen `genai-fastapi:s09`, `IfNotPresent`, puerto 8000 y readiness `/health` con espera inicial y período de cinco segundos. Pide 100m CPU/128 MiB y limita a 500m/512 MiB por réplica. El chatbot sigue en [Compose](http://localhost:8000).

consultar la dirección del host vista desde Minikube:
```powershell
.\.local\bin\minikube.exe --profile=genai ssh -- getent hosts host.minikube.internal
```

Aquí devolvió `192.168.65.254`. Si cambia en otro equipo o perfil, actualiza `postgres.host` en `deploy/helm/fastapi/values.yaml` y `POSTGRES_HOST` en `evidencias/s09/040-pod-sql.yaml` antes de probar. PostgreSQL debe estar arriba y publicado en 5432.

crear o actualizar namespace genai y Secret genai-postgres desde tu .env:
```powershell
.\scripts\crear_secret_postgres.ps1
```

El script lee `POSTGRES_USER` y `POSTGRES_PASSWORD`, exige `POSTGRES_DB=genai` y envía el Secret por stdin. No imprime claves ni las escribe en el chart; repetirlo actualiza el mismo Secret.

validar el chart:
```powershell
.\.local\bin\helm.exe lint deploy/helm/fastapi
```

ver los manifiestos que genera para namespace genai:
```powershell
.\.local\bin\helm.exe template fastapi deploy/helm/fastapi --namespace genai
```

crear el pod temporal que prueba SELECT 1 con la imagen ya cargada y el Secret:
```powershell
.\.local\bin\kubectl.exe --context=genai apply -f evidencias/s09/040-pod-sql.yaml
```

esperar a que termine correctamente:
```powershell
.\.local\bin\kubectl.exe --context=genai -n genai wait '--for=jsonpath={.status.phase}=Succeeded' pod/postgres-check-hdu040 --timeout=90s
```

ver el resultado (debe mostrar 1):
```powershell
.\.local\bin\kubectl.exe --context=genai -n genai logs pod/postgres-check-hdu040
```

borrar solo el pod temporal al terminar:
```powershell
.\.local\bin\kubectl.exe --context=genai -n genai delete pod postgres-check-hdu040 --wait=true
```

Lint, render y SELECT 1 pasaron; el pod se limpió. El cambio de publicación de PostgreSQL conservó cuatro pacientes Python y tres Java. [Evidencias HDU-040](evidencias/s09/040-helm.md). Esta preparación todavía no instala el Deployment de FastAPI.

## Preparar Argo CD

El clúster genai debe estar Ready. El script usa el manifiesto oficial de Argo CD 3.5.6, verifica su SHA-256, crea el namespace `argocd` si falta y aplica los recursos sin forzar conflictos. Espera los deployments, el controlador y los pods; no crea una Application de FastAPI.

instalar o comprobar Argo CD:
```powershell
.\scripts\instalar_argocd.ps1
```

La instalación pasó y dejó siete pods Ready. [Versiones y estado](evidencias/s09/041-instalacion.json), [componentes](evidencias/s09/041-componentes.txt).

abrir o reutilizar el acceso local de Argo CD desde PowerShell 7:
```powershell
.\scripts\abrir_argocd.ps1
```

El script mantiene el port-forward en segundo plano, solo en 127.0.0.1:8443. Comprueba `/api/version` por HTTPS antes de reutilizarlo y mientras espera el arranque; repetirlo reutiliza el proceso sano. Usa `-SkipCertificateCheck` para el certificado local, un parámetro que Windows PowerShell 5.1 no tiene. Si el acceso falla después de reiniciar Minikube, vuelve a ejecutar este comando desde PowerShell 7. Se probaron un nuevo túnel y su reutilización en [HDU-044](evidencias/s10/044-argocd-tunel.json). Abre [Argo CD](https://localhost:8443) y entra como **admin**. Esta instalación local usa certificado autofirmado.

consultar la clave inicial solo en tu terminal (no pegarla en capturas ni evidencias):
```powershell
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((& .\.local\bin\kubectl.exe --context=genai -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}')))
```

registrar el repositorio público en Argo CD:
```powershell
.\.local\bin\kubectl.exe --context=genai apply -f deploy/argocd/repositorio.yaml
```

repetir la lectura histórica del chart de HDU-040 (no comprueba el despliegue actual):
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_repo_argocd.py --commit 1bc6af1235a6d96952334e41685c3acd829b3fed
```

Ese SHA corresponde a la evidencia histórica de conexión; no es una revisión esperada del despliegue actual. El verificador usa la clave inicial en memoria y no la imprime. Comprueba **Successful** y `deploy/helm/fastapi` de tipo Helm; repetirlo regenera `041-repositorio.json`. En la web, ve a **Settings → Repositories**: esa conexión también se comprobó visualmente. [Resultados y captura](evidencias/s09/041-repositorio.md).

El repo es público, así que `repositorio.yaml` no lleva credenciales Git. Los PID/logs del port-forward quedan en `.local`, ignorados por Git. No hay bloqueos activos de lectura Git; el primer error del verificador se corrigió al indicar el proyecto `default`. La Application y el despliegue corresponden a HDU-042.

## FastAPI desde Git

Argo CD sigue `main` y el chart `deploy/helm/fastapi` hacia namespace `genai`, con auto-sync, prune y selfHeal. PostgreSQL de Compose debe estar disponible y el Secret preparado. Esta parte despliega el CRUD; el chatbot sigue en `http://localhost:8000`.

crear o actualizar la Application declarada en Git:
```powershell
.\.local\bin\kubectl.exe --context=genai apply -f deploy/argocd/fastapi.yaml
```

abrir o reutilizar el acceso al Service de FastAPI en Minikube:
```powershell
.\scripts\abrir_fastapi_minikube.ps1
```

El helper deja el port-forward en segundo plano, solo en 127.0.0.1:8002, y comprueba `/health` antes de reutilizarlo. Si pierdes el acceso después de reemplazar un pod, vuelve a ejecutar el mismo comando. Se probaron el inicio de un túnel nuevo tras fallar el anterior y la reutilización de uno sano; sus logs y PID quedan en `.local`.

consultar a Ana en Kubernetes (200):
```powershell
curl.exe -i http://localhost:8002/patients/1
```

ver el estado actual y la revisión de la última operación de Argo CD:
```powershell
.\.local\bin\kubectl.exe --context=genai -n argocd get application fastapi -o 'custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,REVISION:.status.sync.revision,OPERACION:.status.operationState.phase,REVISION_OPERACION:.status.operationState.syncResult.revision'
```

ver las réplicas disponibles del Deployment:
```powershell
.\.local\bin\kubectl.exe --context=genai -n genai get deployment fastapi
```

El estado vigente después de HDU-048 es **dos réplicas Ready**. Comprueba Synced/Healthy, pods Ready y el GET de Ana 200. Un push que solo cambia documentación puede actualizar REVISION sin repetir la última operación de escala, por lo que REVISION_OPERACION puede ser anterior. Las evidencias [HDU-043](evidencias/s09/gitops.md), [HDU-046](evidencias/s10/gitops-preparacion.md) y [HDU-048](evidencias/s10/evaluacion.md) conservan sus SHA históricos; no los uses como expectativas permanentes del estado actual.

`verificar_gitops.py` exige además que la operación Succeeded corresponda al SHA exacto. Úsalo inmediatamente después de un **cambio real de réplicas**, con el SHA nuevo que acabas de publicar, como muestra la [secuencia preparada para la demo](evidencias/s10/gitops-preparacion.md#cambio-preparado-para-la-demo-final). No cambies status ni fuerces una operación solo para hacer coincidir un SHA documental.

Si reaparece **counter cannot decrease in value**:

1. Abre [la Application fastapi](https://localhost:8443/applications/argocd/fastapi) y conserva el mensaje y commit del intento.
2. Pulsa **Sync**, selecciona **main** como revisión y confirma la sincronización. En la prueba, pedir el SHA directamente fue rechazado porque auto-sync sigue main.
3. Espera Synced/Healthy y que la operación indique Succeeded; vuelve a ejecutar el verificador con el commit esperado. No basta con ver el pod funcionando.

El error reapareció en HDU-046; el reintento sobre el mismo commit volvió a terminar correctamente. Se preservaron ambos errores y los tiempos negativos, sin modificar status ni relojes. Es una limitación externa recurrente, no una corrección definitiva. [Primer caso](evidencias/s09/despliegue-inicial.md) y [recurrencia, reintento y captura final](evidencias/s10/gitops-preparacion.md).

## Dos réplicas y reposición

En la prueba histórica HDU-043, `replicaCount: 2` se sincronizó automáticamente desde Git, sin Sync ni refresh manual. HDU-046 lo dejó en **1** para el ensayo; HDU-048 volvió a **2** automáticamente. Para repetir el recorrido, primero [restablece una réplica por Git](evidencias/s10/gitops-preparacion.md#volver-a-una-réplica-para-otra-demo) y después usa [la secuencia 1→2](evidencias/s10/gitops-preparacion.md#cambio-preparado-para-la-demo-final).

ver los pods de FastAPI (ahora deben aparecer dos, cada uno 1/1 Running):
```powershell
.\.local\bin\kubectl.exe --context=genai -n genai get pods -l app=fastapi -o wide
```

La prueba eliminó exactamente uno de los dos pods. Kubernetes creó otro con nombre y UID distintos, mantuvo el otro pod y volvió a dejar dos Ready. No hizo falta otro commit: el Deployment ya pedía dos réplicas. El GET final de Ana en 8002 respondió 200. [Cambio desde Git, reposición y captura](evidencias/s09/gitops.md).

Si el túnel estaba ligado al pod eliminado, repite `abrir_fastapi_minikube.ps1` antes de consultar 8002. En HDU-043 el proceso viejo había terminado; en HDU-046 sí se ejercitó la recuperación del listener propio sin respuesta y el acceso final volvió a dar 200. La explicación personal y la revisión de Rui siguen pendientes.

## Repetir la observabilidad

El ensayo HDU-045 hizo 50 GET en 124,1 segundos y comprobó req/s, error % y p95 de las dos APIs. Después siguió una pregunta de Ana por siete logs y cinco spans. [Resultados, consultas y capturas](evidencias/s10/observabilidad.md).

repetir los 20 GET válidos y 5 inexistentes por API:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/generar_trafico.py --output evidencias/s10/045-peticiones.json
```

Al terminar, usa [la comprobación del dashboard](#revisar-el-dashboard) con `EVIDENCE_DIR` en `evidencias/s10` y un prefijo nuevo; revisa el intervalo que contiene tu carga. Los seis paneles deben tener datos numéricos. Sus métricas incluyen health y scrapes; no representan solo tus 50 peticiones.

enviar la pregunta de Ana y comprobar una nueva traza con sus logs:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_traza.py --prefix hdu045 --output evidencias/s10/045-traza.json
```

Abre la URL que imprime el verificador y usa su request_id en Explore, con la fuente Loki. Añade `| event="llm"` al filtro por id para ver las ramas direct y rag con prompt, respuesta y duración. En Phoenix comprueba `retrieval → prompt → llamada_llm → respuesta` bajo `rag`. [Consulta exacta y ejemplo comprobado](evidencias/s10/observabilidad.md#la-misma-pregunta-en-loki-y-phoenix).

Ojo: estos comandos regeneran sus JSON; cambia las rutas de `--output` para conservar la ejecución anterior. El request_id será nuevo. La explicación personal y la revisión de Rui siguen pendientes.

## Comprobar el entorno completo

Primero sigue el arranque del README, espera las APIs e inicia Ollama. Para la parte Kubernetes, el perfil genai debe estar arriba y los helpers de Argo CD y FastAPI deben haber abierto 8443 y 8002. El verificador solo consulta; no arranca servicios.

comprobar los ocho accesos locales y guardar el resultado:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_componentes.py --output evidencias/s10/044-componentes.json
```

Comprueba FastAPI, Spring Boot, chatbot, Grafana, Phoenix, Argo CD, Loki y Ana en Minikube. Guarda también los fallos y termina con error si alguno no responde correctamente. Ojo: ese comando regenera el JSON; cambia `--output` si quieres conservar la ejecución anterior.

En HDU-044 los ocho accesos devolvieron 200. También pasaron los verificadores CRUD de ambas APIs, conservando cuatro filas Python y tres Java, y la pregunta de Ana mostró ambas respuestas y la fuente de Enfermedad Alfa. [Fallos, correcciones y repeticiones](evidencias/s10/fallos.md). El arranque completo desde detenido continúa sin ejecutar; estas comprobaciones usan el entorno existente.

## Guion final

Abre [el guion de S10](evidencias/s10/guion.md): trae comandos, URLs, resultados esperados y las evidencias HDU-044 a HDU-046. El ensayo de consultas HDU-047 comprobó Ana en los tres accesos, nueve puntos Qdrant, dos targets UP, los eventos LLM, cinco spans y una réplica Ready.

Ese ensayo fue anterior a HDU-048, que dejó **dos réplicas**. Si quieres repetir la demo desde una, usa el restablecimiento por Git del guion antes del paso 1→2. [Resultado técnico y pendientes](evidencias/s10/evaluacion.md). Las frases por componente sirven para repasar; explicación propia, sesión y valoración de Rui siguen pendientes.

## Revisar el equipo

versiones:
```bash
git --version
```
```bash
docker --version
```
```bash
docker compose version
```

RAM libre (PowerShell):
```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object @{n='TotalGB';e={[math]::Round($_.TotalVisibleMemorySize/1MB,2)}}, @{n='LibreGB';e={[math]::Round($_.FreePhysicalMemory/1MB,2)}}
```
