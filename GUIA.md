# Guía rápida

Todo se corre desde la carpeta del proyecto (`GenAIRUIFormacion2026`). Docker Desktop tiene que estar abierto.

## Primera vez

crear tu .env (después pon usuario y clave):
```bash
cp .env.example .env
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
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

## python-api

probar que la api está viva (debe responder 200 y {"status":"ok"}):
```bash
curl -i http://localhost:8000/health
```

documentación automática de FastAPI: abrir http://localhost:8000/docs en el navegador.

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
