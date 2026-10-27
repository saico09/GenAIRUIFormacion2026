# Historial de la app

Qué se ha ido agregando, qué es y cómo se usa. Lo más nuevo arriba. Comandos completos en [GUIA.md](GUIA.md).

## HDU-002 · 27/10/2026 · Crear y consultar pacientes

- **Tabla `public.patients`** (id autogenerado, name, birth_date, email). La crea la API al arrancar si no existe; no borra datos.
- **`POST /patients`** guarda un paciente y responde 201 con su id. **`GET /patients`** lista todos y **`GET /patients/{id}`** trae uno.
- **Validaciones** en `app/schemas.py`: name no vacío, birth_date `YYYY-MM-DD` de una fecha real y email válido. Si algo falla, responde 422 y no guarda nada.
- **Código separado**: `db.py` conexión (variables de entorno), `models.py` la tabla, `schemas.py` validaciones, `main.py` endpoints.
- **`datos/pacientes.json`**: Ana, Bruno y Carla Demo (ficticios). Ya cargados: ids 1, 2 y 3.
- Ojo: un id que no existe todavía da 500; el 404 llega en la HDU-003.

## HDU-001 · 27/10/2026 · PostgreSQL + FastAPI en Docker

- **codigo/** es el repo de Git; todo lo de la app vive ahí, separado de los documentos del programa.
- **compose.yml**: levanta dos servicios con `docker compose up -d --build`.
- **postgres** (18.6-alpine): base `genai`. Usuario y clave salen del `.env` (no va a Git). Los datos viven en el volumen `pgdata`, así que sobreviven a un `down`. Tiene healthcheck con `pg_isready`. Publicado en `localhost:5432` (solo este equipo) para entrar con DBeaver.
- **python-api** (Python 3.15 + FastAPI): por ahora solo `GET /health`, que responde `{"status":"ok"}` en http://localhost:8000. Espera a que postgres esté sano antes de arrancar. Ya trae instaladas SQLAlchemy, psycopg y email-validator para el CRUD de la HDU-002, pero todavía no se conecta a la base.
- **.env.example**: los nombres de las variables, sin valores. Se copia como `.env`.
- **datos/** vacía (los pacientes llegan en la HDU-002). **evidencias/S01.md** guarda las pruebas.
- Ojo: el equipo tiene 1,2 GB de RAM libre y el programa pide 8. Resolverlo antes de S3.
