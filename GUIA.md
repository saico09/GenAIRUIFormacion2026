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

levantar todo (postgres + python-api), reconstruyendo si cambiaste código:
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

## Pacientes

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

## Comprobar el CRUD

repetir la prueba completa usando el Python del contenedor (no necesitas instalar Python en Windows):
```powershell
Get-Content -Raw scripts/verificar_crud.py | docker compose exec -T python-api python - --base-url http://localhost:8000
```

El script crea un paciente ficticio, lo consulta, cambia sus tres campos y lo borra. Comprueba 404 en GET/PUT/DELETE, 204 sin cuerpo y 422 para nombre vacío, fecha imposible y email inválido en POST/PUT. Al terminar verifica que los pacientes que había antes siguen iguales. Si falla, intenta limpiar únicamente el paciente que creó y muestra cualquier limpieza pendiente. No edites pacientes desde otra ventana durante la prueba.

`schemas.py` revisa la entrada antes de llegar al endpoint; `main.py` usa la sesión de `db.py`, guarda el modelo de `models.py` y confirma el cambio con `commit()`. `find_patient()` resuelve la búsqueda compartida: si no existe el id, responde 404. No hace falta memorizarlo: sigue un POST y luego un PUT para ver el recorrido.

## Comprobar persistencia

reiniciar postgres y python-api y comprobar que los pacientes siguen iguales:
```powershell
.\scripts\verificar_persistencia.ps1
```

Ojo: durante el reinicio la API deja de responder unos segundos. La prueba necesita que exista Ana Demo original; compara todas las filas y los cuatro campos de Ana antes/después, sin mostrar datos de otros pacientes. No borra el volumen `pgdata`. Evita editar pacientes mientras corre.

`pgdata` conserva los datos aunque el contenedor se reinicie. En `db.py`, `pool_pre_ping=True` comprueba que la conexión siga viva antes de reutilizarla; así descarta conexiones viejas después de un reinicio de PostgreSQL.

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
