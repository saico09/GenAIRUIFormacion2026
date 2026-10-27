# Guía rápida

Todo se corre desde la carpeta `codigo` (es el repo de Git). Docker Desktop tiene que estar abierto.

ojo en PowerShell: usa `curl.exe` y no `curl` a secas (en PowerShell `curl` es otro comando y falla).

entrar a la carpeta:
```bash
cd C:/Users/marco/Documents/CONKORD/GenAIRUIFormacion2026/codigo
```

## Primera vez (solo en un equipo nuevo)

ojo: tu `.env` ya existe. Este paso es solo para un clon nuevo del repo; si lo corres ahora, pisa tu usuario y clave.

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

ver uno por id (ej. Ana es el 1):
```bash
curl.exe -i http://localhost:8000/patients/1
```

crear uno a mano (PowerShell; queda guardado en la base):
```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/patients -ContentType 'application/json' -Body '{"name":"Nombre Demo","birth_date":"1995-05-05","email":"nombre@example.com"}'
```

probar que rechaza datos malos (debe dar error 422 y no guardar nada):
```powershell
try { Invoke-RestMethod -Method Post -Uri http://localhost:8000/patients -ContentType 'application/json' -Body '{"name":"X","birth_date":"2026-02-30","email":"x@example.com"}' } catch { $_.Exception.Response.StatusCode.value__; $_.ErrorDetails.Message }
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
