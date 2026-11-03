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

Para esperar ambas APIs:

```powershell
.\scripts\esperar_apis.ps1
```

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
| Chatbot / Swagger Python | [8000](http://localhost:8000) / [docs](http://localhost:8000/docs) |
| Pacientes Java | [8080/patients](http://localhost:8080/patients) |
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

La [guía](GUIA.md#fastapi-desde-git) explica la comprobación de PostgreSQL y los túneles. Allí se despliega solo el CRUD FastAPI; el chatbot sigue en Compose, puerto 8000.

## Contrato HTTP

Python usa `public.patients`; Java, `java.patients`. POST y PUT reciben `name`, `birth_date` (`YYYY-MM-DD`) y `email`. Cada tabla genera sus propios ids.

| Operación | Correcto | Error |
|---|---|---|
| `POST /patients` | 201, paciente con id | 422 entrada inválida |
| `GET /patients` | 200, lista | — |
| `GET /patients/{id}` | 200, paciente | 404 ausente |
| `PUT /patients/{id}` | 200, paciente | 404 ausente / 422 inválido |
| `DELETE /patients/{id}` | 204, vacío | 404 ausente |
| `POST /chat` (Python) | 200, respuestas directa/RAG y fuentes | 422 entrada / 404 paciente / 503 dependencia |

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
| `datos/` | Tres historias ficticias y cuatro preguntas |
| `observabilidad/` | Prometheus, Grafana, Loki y Alloy |
| `deploy/` | Chart y Application de FastAPI |
| `scripts/` | Arranque y comprobaciones repetibles |
| `evidencias/` | Resultados fechados; no son estado en vivo |

El 03/11 se repitieron arranque, CRUD, persistencia, RAG, observabilidad y escala GitOps: [resultados nuevos](evidencias/revision-claude/LEEME.md). La explicación personal y la evaluación de Rui siguen pendientes.
