# GenAI · app de práctica

Por ahora tenemos PostgreSQL, dos servicios de pacientes —FastAPI y Spring Boot— y tres historias ficticias preparadas para la futura ingesta. Ambas APIs permiten crear, listar, consultar, editar y borrar pacientes. Los comandos son para PowerShell, desde esta carpeta `codigo`, con Docker Desktop abierto.

[Guía de comandos](GUIA.md) · [Qué se ha agregado](HISTORIAL.md) · [Evidencias S01](evidencias/S01.md) · [Evidencias S02](evidencias/S02.md) · [Evidencias S03](evidencias/S03.md) · [Trello](https://trello.com/b/DKjKsa6B/ckd-genairuiformacion2026)

## Arrancar

preparar la configuración solo en un clon nuevo (después completa los valores de `.env`; si ya existe, lo conserva):

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

levantar postgres y las dos apis:

```bash
docker compose up -d --build
```

comprobar que FastAPI responde (200):

```bash
curl.exe -i http://localhost:8000/health
```

comprobar que Spring Boot responde (200):

```bash
curl.exe -i http://localhost:8080/health
```

Abre [Swagger de FastAPI](http://localhost:8000/docs) para probar el CRUD desde el navegador. PostgreSQL escucha en `localhost:5432`; FastAPI en `localhost:8000`; Spring Boot en `localhost:8080`. La base guarda los datos en el volumen `pgdata`.

Python usa `public.patients` y Java usa `java.patients`, dentro de la misma base. Eso permite conservar y probar las filas de cada servicio por separado. En este equipo, Ana, Bruno y Carla Demo ya están cargados en ambas; los ids se generan de forma independiente. En un clon nuevo, usa los comandos de carga de la guía antes de probar persistencia.

## Contrato HTTP

Los cuerpos de POST y PUT llevan `name` (texto no vacío), `birth_date` (fecha real en formato `YYYY-MM-DD`) y `email` (dirección válida). PUT necesita los tres campos. Las respuestas con un paciente también incluyen su `id` entero, generado por PostgreSQL.

| Operación | Disponible en | Respuesta correcta | Error previsto |
|---|---|---|---|
| `GET /health` | Python y Java | 200, `{"status":"ok"}` | — |
| `POST /patients` | Python y Java | 201, paciente creado | 422 si la entrada no es válida |
| `GET /patients` | Python y Java | 200, lista ordenada por id | — |
| `GET /patients/{id}` | Python y Java | 200, paciente | 404 si no existe |
| `PUT /patients/{id}` | Python y Java | 200, paciente actualizado | 404 si no existe; 422 si la entrada no es válida |
| `DELETE /patients/{id}` | Python y Java | 204, sin cuerpo | 404 si no existe |

El 404 de ambas APIs usa `{"detail":"Paciente no encontrado"}`. Se comprobaron 14 entradas inválidas en POST y PUT: nombre vacío o numérico, fechas imposibles o con formato incorrecto, emails inválidos o sin dominio completo y campos ausentes. Cada API devolvió 28 respuestas 422 sin guardar cambios. El detalle interno de los errores 422 puede ser distinto entre frameworks; se comparan los códigos y el efecto en los datos, sin exigir mensajes idénticos.

## Probar cada operación

Esta secuencia usa Python en el puerto 8000. Hazla en la misma ventana de PowerShell: `$prueba.id` conserva el id recién creado. Así editas y borras solo tu registro de prueba. `curl.exe` muestra el código HTTP; `Invoke-RestMethod` muestra el JSON como un objeto de PowerShell.

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

comprobar que los datos Python sobreviven al reinicio:

```powershell
.\scripts\verificar_persistencia.ps1
```

comprobar lo mismo para Java:

```powershell
.\scripts\verificar_persistencia.ps1 -Servicio java-api
```

Cada prueba reinicia PostgreSQL y la API elegida, compara sus filas y confirma los cuatro campos de Ana Demo. Requiere que Ana siga con sus datos originales y no borra `pgdata`. Ojo: durante el reinicio se interrumpe brevemente el acceso a la base para ambas APIs. Más detalle en la [guía](GUIA.md#comprobar-persistencia).

listar los mismos pacientes ficticios en Java (200):

```bash
curl.exe -i http://localhost:8080/patients
```

consultar a Ana en Java (200; id 1 en la carga inicial):

```bash
curl.exe -i http://localhost:8080/patients/1
```

Los comandos para crear, editar y borrar un temporal Java están en la [guía](GUIA.md#pacientes-java). Usa `$pruebaJava.id` para tocar solo el registro que acabas de crear. La carga de Ana, Bruno y Carla ya se ejecutó; repetirla duplica los tres pacientes.

comprobar automáticamente todo el CRUD Java y limpiar su temporal:

```powershell
Get-Content -Raw scripts/verificar_crud.py | docker compose exec -T python-api python - --base-url http://java-api:8080
```

El nombre `java-api` funciona dentro de la red de Docker; desde Windows usas `localhost:8080`. Ejecuta ambos verificadores para repetir la comparación. El CRUD y las 56 respuestas 422 esperadas pasaron entre ambas APIs; quedaron intactas las filas previas. Resultados en [evidencias S02](evidencias/S02.md).

## Datos para la futura ingesta

leer las historias ficticias de Ana, Bruno y Carla:

```powershell
Get-Content -Raw datos/paciente-1.md, datos/paciente-2.md, datos/paciente-3.md
```

leer las cuatro preguntas con su respuesta esperada:

```powershell
Get-Content -Raw datos/preguntas.json
```

Cada historia identifica al paciente por su id Python y tiene Enfermedad, Tratamiento y Medicamento: nueve secciones en total. Tres preguntas se responden desde esos textos. La cirugía de Ana no está documentada, así que se espera `No hay información suficiente`.

**HDU-011 bloqueada por RAM:** la última medición dio 0,32 GB libres de 13,86 GB, frente al mínimo de 8 GB del programa. Todavía no hay embeddings, Qdrant ni RAG implementados. El siguiente paso es liberar memoria o disponer de recursos autorizados, volver a [medir la RAM](GUIA.md#revisar-el-equipo) y reanudar HDU-011 cuando se cumpla el mínimo.

## Ubicarse en el código

| Archivo | Para qué sirve |
|---|---|
| `compose.yml` | Arranca los servicios y conserva PostgreSQL en `pgdata`. |
| `python-api/app/main.py` | Endpoints y búsqueda que responde 404. |
| `python-api/app/schemas.py` | Valida lo que entra y define el JSON de salida. |
| `python-api/app/models.py` | Define la tabla `public.patients`. |
| `python-api/app/db.py` | Abre la conexión y entrega una sesión por petición. |
| `java-api/pom.xml` | Dependencias y versión de Spring Boot; Maven construye el servicio. |
| `java-api/src/main/resources/application.properties` | Configura la conexión de Java usando las variables de Compose. |
| `java-api/src/main/resources/schema.sql` | Crea el esquema `java` si todavía no existe. |
| `java-api/src/main/java/com/conkord/genai/PatientController.java` | Recibe las peticiones de pacientes y usa el repositorio JPA. |
| `java-api/src/main/java/com/conkord/genai/PatientRequest.java` | Valida nombre, fecha y email recibidos por Java. |
| `datos/pacientes.json` | Los tres pacientes ficticios iniciales. |
| `datos/paciente-1.md` a `paciente-3.md` | Historias ficticias vinculadas a los ids de Python. |
| `datos/preguntas.json` | Cuatro preguntas y respuestas esperadas para probar recuperación. |
| `scripts/verificar_crud.py` | Prueba reproducible por HTTP; limpia su paciente temporal. |
| `scripts/verificar_persistencia.ps1` | Reinicia servicios y compara los pacientes antes/después. |

El recorrido Python es JSON → validación → endpoint → sesión SQLAlchemy → PostgreSQL → respuesta. En Java es JSON → `PatientRequest` → controlador → repositorio JPA → PostgreSQL → respuesta. El código y las pruebas no acreditan todavía la explicación de Marco ni la revisión de Rui; esos pendientes se registran aparte.
