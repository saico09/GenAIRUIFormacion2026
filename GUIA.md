# Guía rápida

Todo se corre desde la carpeta `codigo` (es el repo de Git), en PowerShell. Docker Desktop tiene que estar abierto. La entrada rápida y el contrato HTTP están en [README.md](README.md).

ojo en PowerShell: usa `curl.exe` y no `curl` a secas (en PowerShell `curl` es otro comando y falla).

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

## Levantar / bajar

levantar los contenedores (postgres + python-api + java-api + qdrant), reconstruyendo si cambiaste código:
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

bajar los contenedores (los datos se mantienen en pgdata y qdrant_data; Ollama corre aparte en Windows):
```bash
docker compose down
```

bajar los contenedores y BORRAR pacientes y vectores (ojo: elimina pgdata y qdrant_data):
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
