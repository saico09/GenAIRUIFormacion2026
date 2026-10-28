# Historial de la app

Qué se ha ido agregando, qué es y cómo se usa. Lo más nuevo arriba. Comandos completos en [GUIA.md](GUIA.md).

Cada entrada cuenta lo que había en esa fecha; las limitaciones antiguas pueden estar resueltas en una entrada posterior. El estado actual se resume en [README.md](README.md).

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
