# Historial de la app

Qué se ha ido agregando, qué es y cómo se usa. Lo más nuevo arriba. Comandos completos en [GUIA.md](GUIA.md).

## HDU-001 · 27/10/2026 · PostgreSQL + FastAPI en Docker

- **codigo/** es el repo de Git; todo lo de la app vive ahí, separado de los documentos del programa.
- **compose.yml**: levanta dos servicios con `docker compose up -d --build`.
- **postgres** (18.6-alpine): base `genai`. Usuario y clave salen del `.env` (no va a Git). Los datos viven en el volumen `pgdata`, así que sobreviven a un `down`. Tiene healthcheck con `pg_isready`.
- **python-api** (Python 3.15 + FastAPI): por ahora solo `GET /health`, que responde `{"status":"ok"}` en http://localhost:8000. Espera a que postgres esté sano antes de arrancar. Ya trae instaladas SQLAlchemy, psycopg y email-validator para el CRUD de la HDU-002, pero todavía no se conecta a la base.
- **.env.example**: los nombres de las variables, sin valores. Se copia como `.env`.
- **datos/** vacía (los pacientes llegan en la HDU-002). **evidencias/S01.md** guarda las pruebas.
- Ojo: el equipo tiene 1,2 GB de RAM libre y el programa pide 8. Resolverlo antes de S3.
