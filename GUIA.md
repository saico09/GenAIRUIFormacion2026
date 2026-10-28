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

levantar todo (postgres + python-api + java-api), reconstruyendo si cambiaste código:
```bash
docker compose up -d --build
```

ver qué está corriendo:
```bash
docker compose ps
```

bajar todo (los datos se mantienen en el volumen pgdata):
```bash
docker compose down
```

bajar todo y BORRAR la base (ojo, no hay vuelta atrás):
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

Ana, Bruno y Carla ya están cargados en Java. Los campos JSON son los mismos que en Python: `name`, `birth_date` y `email`; cada tabla genera sus propios ids, así que no dependas de que coincidan entre APIs.

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
