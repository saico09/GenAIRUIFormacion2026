# GenAI · app de práctica

Por ahora tenemos PostgreSQL y una API de pacientes con FastAPI: crear, listar, consultar, editar y borrar. Usa datos ficticios. Los comandos son para PowerShell, desde esta carpeta `codigo`, con Docker Desktop abierto.

[Guía de comandos](GUIA.md) · [Qué se ha agregado](HISTORIAL.md) · [Evidencias de S01](evidencias/S01.md) · [Trello](https://trello.com/b/DKjKsa6B/ckd-genairuiformacion2026)

## Arrancar

preparar la configuración solo en un clon nuevo (después completa los valores de `.env`; si ya existe, lo conserva):

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

levantar postgres y la api:

```bash
docker compose up -d --build
```

comprobar que responde (200):

```bash
curl.exe -i http://localhost:8000/health
```

Abre [Swagger](http://localhost:8000/docs) para probar la API desde el navegador. PostgreSQL escucha en `localhost:5432`; la API en `localhost:8000`. La base guarda los datos en el volumen `pgdata`.

## Contrato HTTP

Los cuerpos de POST y PUT llevan `name` (texto no vacío), `birth_date` (fecha real en formato `YYYY-MM-DD`) y `email` (dirección válida). PUT necesita los tres campos. Las respuestas con un paciente también incluyen su `id` entero, generado por PostgreSQL.

| Operación | Respuesta correcta | Error previsto |
|---|---|---|
| `GET /health` | 200, `{"status":"ok"}` | — |
| `POST /patients` | 201, paciente creado | 422 si la entrada no es válida |
| `GET /patients` | 200, lista ordenada por id | — |
| `GET /patients/{id}` | 200, paciente | 404 si no existe |
| `PUT /patients/{id}` | 200, paciente actualizado | 404 si no existe; 422 si la entrada no es válida |
| `DELETE /patients/{id}` | 204, sin cuerpo | 404 si no existe |

Un id con formato no entero también devuelve 422. El 404 usa `{"detail":"Paciente no encontrado"}`. Las validaciones 422 indican el campo que falló y no guardan cambios.

## Probar cada operación

Haz la secuencia en la misma ventana de PowerShell: `$prueba.id` conserva el id recién creado. Así editas y borras solo tu registro de prueba. `curl.exe` muestra el código HTTP; `Invoke-RestMethod` muestra el JSON como un objeto de PowerShell.

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

comprobar que los datos sobreviven al reinicio (interrumpe la API unos segundos):

```powershell
.\scripts\verificar_persistencia.ps1
```

La prueba compara todas las filas y confirma los cuatro campos de Ana Demo. Requiere que Ana siga con sus datos originales y no borra `pgdata`. Más detalle en la [guía](GUIA.md#comprobar-persistencia).

## Ubicarse en el código

| Archivo | Para qué sirve |
|---|---|
| `compose.yml` | Arranca los servicios y conserva PostgreSQL en `pgdata`. |
| `python-api/app/main.py` | Endpoints y búsqueda que responde 404. |
| `python-api/app/schemas.py` | Valida lo que entra y define el JSON de salida. |
| `python-api/app/models.py` | Define la tabla `public.patients`. |
| `python-api/app/db.py` | Abre la conexión y entrega una sesión por petición. |
| `datos/pacientes.json` | Los tres pacientes ficticios iniciales. |
| `scripts/verificar_crud.py` | Prueba reproducible por HTTP; limpia su paciente temporal. |
| `scripts/verificar_persistencia.ps1` | Reinicia servicios y compara los pacientes antes/después. |

El recorrido es: JSON → validación → endpoint → sesión SQLAlchemy → PostgreSQL → respuesta. El código y las pruebas no acreditan todavía la explicación de Marco ni la revisión de Rui; esos pendientes se registran aparte.
