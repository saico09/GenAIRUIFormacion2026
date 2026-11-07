# GenAI · app de práctica

CRUD Python y Java, chatbot con/sin RAG, métricas, logs, trazas y GitOps local. Usa **PowerShell 7**, **Python 3** y Docker Desktop; ejecuta los comandos desde `codigo/`.

[Guía de comandos](GUIA.md) · [Historial breve](HISTORIAL.md) · [Demo S5](evidencias/S05-guion.md) · [Demo final](evidencias/s10/guion.md) · [Resultados y pendientes](evidencias/s10/evaluacion.md)

## Arrancar

Para preparar un clon nuevo:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Completa usuario y claves en `.env`; conserva el que ya tienes y no lo compartas.

Para levantar los contenedores:

```powershell
docker compose up -d --build
```

Compose monta `datos/historias/` en Java con escritura: ahí se conservan los informes `.md`. No cambies ese montaje a solo lectura ni borres la carpeta al reiniciar.

Para esperar ambas APIs:

```powershell
.\scripts\esperar_apis.ps1
```

Para cargar los tres pacientes Java de la demo y asociarlos a sus informes:

```powershell
docker compose exec -T python-api python inicializar_java.py
```

Solo carga una tabla Java vacía, con los IDs 1–3 del dataset. Si ya hay pacientes, responde `conservados` y no modifica filas, informes ni secuencia. No uses los POST individuales para esta primera asociación: Java protege los informes que ya existen.

Para iniciar o reutilizar Ollama:

```powershell
.\scripts\iniciar_ollama.ps1
```

Para comprobar Python:

```powershell
curl.exe -i http://localhost:8000/health
```

Para comprobar Java:

```powershell
curl.exe -i http://localhost:8080/health
```

## Abrir

| Qué | Dónde |
|---|---|
| Consultas con y sin RAG | [Consultas médicas](http://localhost:8000/#consultas) |
| Administrar pacientes Java | [Pacientes](http://localhost:8000/#pacientes) |
| Probar endpoints | [API Python](http://localhost:8000/#api-python) / [API Java](http://localhost:8000/#api-java) |
| Swagger Python | [docs](http://localhost:8000/docs) |
| PostgreSQL | `localhost:5432`, credenciales en `.env` |
| Qdrant | [6333/dashboard](http://localhost:6333/dashboard) |
| Prometheus | [9090/targets](http://localhost:9090/targets) |
| Grafana | [3000](http://localhost:3000/d/genai-apis/apis-genai), usuario `admin` |
| Loki | [3100/ready](http://localhost:3100/ready) |
| Phoenix | [6006](http://localhost:6006) |
| FastAPI en Minikube | [8002/patients](http://localhost:8002/patients) |
| Argo CD | [8443](https://localhost:8443), certificado local |

Para reanudar Minikube ya preparado:

```powershell
.\scripts\reanudar_minikube.ps1
```

El comando conecta PostgreSQL directamente a la red del perfil y comprueba SQL antes de abrir los túneles. Necesita Docker Desktop respondiendo. [Preparación inicial](GUIA.md#preparar-minikube): solo se despliega el CRUD FastAPI; el chatbot sigue en Compose, puerto 8000.

## Contrato HTTP

Python usa `public.patients`; Java, `java.patients`. POST y PUT reciben `name`, `birth_date` (`YYYY-MM-DD`) y `email`. Cada tabla genera sus propios ids.

En **Pacientes**, pulsa el nombre para abrir su historia: tabla con UUID, enfermedad, tratamiento y medicamento; archivo Markdown visible, descargable y editable. **Nueva consulta → Preparar con IA → revisar campos → confirmar** añade un registro. La IA extrae hechos escritos en tu nota ficticia; también puedes crear el registro manualmente.

**Consultas médicas** usa estos mismos pacientes Java y sus informes. Preguntar no guarda respuestas: **Preparar registro** lleva solo tu pregunta como borrador para revisarla. Python conserva su CRUD de práctica independiente. Los exploradores ejecutan peticiones reales y eliminar pide confirmación.

| Operación | Correcto | Error |
|---|---|---|
| `POST /patients` | 201, paciente con id | 422 entrada inválida |
| `GET /patients` | 200, lista | — |
| `GET /patients/{id}` | 200, paciente | 404 ausente |
| `PUT /patients/{id}` | 200, paciente | 404 ausente / 422 inválido |
| `DELETE /patients/{id}` | 204, vacío | 404 ausente |
| `POST /chat` (Python) | 200, respuestas directa/RAG y fuentes | 422 entrada / 404 paciente / 503 dependencia |
| `GET /patients/{id}/history` (Java) | 200, Markdown, revisión y registros | 404 paciente |
| `GET /patients/{id}/history.md` (Java) | 200, descarga Markdown | 404 paciente |
| `PUT /patients/{id}/history` (Java) | 200, informe actualizado | 409 revisión antigua / 422 inválido |
| `POST /patients/{id}/history/entries` (Java) | 201, informe con nuevo registro | 409 revisión antigua / 422 inválido |
| `POST /clinical/proposals` (Python) | 200, propuestas editables y evidencia | 422 entrada / 404 paciente / 503 dependencia |
| `POST /clinical/patients/{id}/sync` (Python) | 200, índice sincronizado o retirado | 503 dependencia |

El Markdown es la fuente de los hechos clínicos; PostgreSQL guarda los datos básicos del paciente y Qdrant su índice de búsqueda. Los cambios del informe necesitan revisión vigente y confirmación. Un 409 conserva el borrador: recarga la historia y revísalo antes de guardar. [Uso breve](GUIA.md#historia-clínica).

## Probar cada operación

Para elegir la API (usa `8080` para repetirlo en Java):

```powershell
$api = 'http://localhost:8000'
```

Para crear un temporal y conservar su id:

```powershell
$prueba = Invoke-RestMethod -Method Post -Uri "$api/patients" -ContentType 'application/json' -Body '{"name":"Prueba Guia","birth_date":"1995-05-05","email":"guia@example.com"}'
```

Para listar:

```powershell
curl.exe -i "$api/patients"
```

Para consultar el temporal:

```powershell
curl.exe -i "$api/patients/$($prueba.id)"
```

Para editarlo:

```powershell
Invoke-RestMethod -Method Put -Uri "$api/patients/$($prueba.id)" -ContentType 'application/json' -Body '{"name":"Prueba Editada","birth_date":"1996-06-06","email":"editada@example.com"}'
```

Para borrar solo ese temporal:

```powershell
curl.exe -i -X DELETE "$api/patients/$($prueba.id)"
```

Para comprobar el 404 posterior:

```powershell
curl.exe -i "$api/patients/$($prueba.id)"
```

Haz la secuencia en la misma terminal. [La guía](GUIA.md#comprobar-el-crud) incluye las pruebas completas, persistencia y carga inicial.

## Ubicarse

| Carpeta | Para qué |
|---|---|
| `python-api/`, `java-api/` | APIs y chatbot |
| `datos/` | Dataset ficticio y preguntas de prueba; informes vigentes en `historias/` |
| `observabilidad/` | Prometheus, Grafana, Loki y Alloy |
| `deploy/` | Chart y Application de FastAPI |
| `scripts/` | Arranque y comprobaciones repetibles |
| `evidencias/` | Resultados fechados; no son estado en vivo |

El 07/11 se añadió la navegación, la administración con Java y los exploradores de endpoints: [pruebas de la interfaz](evidencias/ui-2026-11-07/LEEME.md). El [ensayo completo del 03/11](evidencias/revision-claude/LEEME.md) conserva las comprobaciones de observabilidad y GitOps. La explicación personal y la evaluación de Rui siguen pendientes.

La gestión de historias y el registro asistido por IA son una ampliación solicitada por Marco el 07/11; no cambian las HDU ni constituyen una evaluación de Rui. [Recorrido de pantalla comprobado con LLM real](evidencias/clinica-2026-11-07/interfaz.md): propuesta revisada, guardado, edición, consulta RAG y limpieza, conservando los datos previos.
