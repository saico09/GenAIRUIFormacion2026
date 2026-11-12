# GenAI · app de práctica

CRUD Python y Java, chatbot con/sin RAG, métricas, logs, trazas y GitOps local. Usa **PowerShell 7**, **Python 3** y Docker Desktop; ejecuta los comandos desde `codigo/`.

Los [casos de prueba](datos/CASOS.md) usan pacientes inventados con reflujo gastroesofágico, diabetes tipo 2 y rinitis alérgica, más tratamientos y medicamentos reales.

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

Compose monta `datos/historias/` en ambas APIs con escritura: ahí se conservan los informes `.md`. No cambies ese montaje a solo lectura ni borres la carpeta al reiniciar.

Para esperar ambas APIs:

```powershell
.\scripts\esperar_apis.ps1
```

Para cargar los tres pacientes de la demo y asociarlos a sus informes:

```powershell
docker compose exec -T python-api python inicializar_datos.py
```

La carga inicial conserva los IDs 1–3 de la demo y protege los datos existentes. Después crea tus pacientes desde la página o cualquiera de las dos APIs: cada alta genera su Markdown automáticamente.

Para iniciar o reutilizar Ollama:

```powershell
.\scripts\iniciar_ollama.ps1
```

Para descargar los modelos de embeddings y chat, si todavía faltan:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull nomic-embed-text
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull qwen3.5:4b-q4_K_M
```

Ollama es el servidor local que ejecuta los modelos. Qwen 3.5 de 4B (`qwen3.5:4b-q4_K_M`) responde en ambas ramas con los mismos parámetros, temperatura `0.2` y `think=false`. El modelo propone causas y condiciones en una estructura que Python valida y presenta como texto. Los [ensayos y sus límites](evidencias/revision-funcional-2026-11-11/LEEME.md) corresponden a casos ficticios concretos.

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
| Administrar pacientes y registros | [Pacientes](http://localhost:8000/#pacientes) |
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

Minikube y Argo CD son opcionales para practicar GitOps: `docker compose up` no los inicia. Postman usa las APIs de Compose. Para reanudar Minikube ya preparado:

```powershell
.\scripts\reanudar_minikube.ps1
```

El comando conecta PostgreSQL, comparte `datos/historias` con las dos réplicas y comprueba lectura, escritura y SQL antes de abrir los túneles. Recupera el montaje si se perdió. Necesita Docker Desktop respondiendo. [Preparación inicial](GUIA.md#preparar-minikube): se despliega el CRUD FastAPI; el chatbot sigue en Compose, puerto 8000.

Para detener ese perfil antes de cambiar de semana:

```powershell
.\.local\bin\minikube.exe stop --profile=genai
```

La versión principal y las diez copias semanales usan estos mismos puertos. Ejecuta una sola a la vez; cada semana conserva sus propios volúmenes.

## Contrato HTTP

Python y Java usan el mismo registro `public.patients`: un paciente creado en una API aparece en la otra y en la página. POST y PUT reciben `name`, `birth_date` (`YYYY-MM-DD`) y `email`. El ID del paciente se conserva al editarlo.

En **Pacientes**, pulsa un nombre para abrir su historia. **Registros confirmados → Agregar registro** permite completar enfermedad, tratamiento y medicamento; cada fila tiene **Editar** y **Eliminar**. Los cambios actualizan `patient_diseases` y el Markdown, con el mismo UUID. **Preparar desde una nota** conserva la opción de extraer una propuesta con IA y revisarla antes de guardar.

**Consultas médicas → Comparar y guardar** guarda automáticamente tu consulta y ambas respuestas en el informe y en PostgreSQL. El mensaje de guardado muestra su UUID y permite abrir el informe. Las respuestas quedan como orientación de IA, separadas de los diagnósticos confirmados.

Si describes síntomas, la IA plantea una hipótesis principal y alternativas condicionales, sin pedir más datos ni repetir preguntas. Son posibilidades para el caso ficticio; no se añaden como enfermedades confirmadas. Si preguntas por un dato del historial, RAG sólo usa lo documentado y reconoce cuando ese dato falta.

| Operación | Correcto | Error |
|---|---|---|
| `POST /patients` | 201, paciente con id | 422 entrada inválida |
| `GET /patients` | 200, lista | — |
| `GET /patients/{id}` | 200, paciente | 404 ausente |
| `PUT /patients/{id}` | 200, paciente | 404 ausente / 422 inválido |
| `DELETE /patients/{id}` | 204, vacío | 404 ausente |
| `GET /patients/{id}/diseases` (ambas) | 200, registros del paciente | 404 paciente |
| `POST /patients/{id}/diseases` (ambas) | 201, registro con UUID | 404 paciente / 422 inválido |
| `GET /patients/{id}/diseases/{uuid}` (ambas) | 200, registro | 404 ausente o de otro paciente |
| `PUT /patients/{id}/diseases/{uuid}` (ambas) | 200, registro actualizado | 404 ausente / 422 inválido |
| `DELETE /patients/{id}/diseases/{uuid}` (ambas) | 204, vacío | 404 ausente |
| `POST /chat` (Python) | 200, respuestas, fuentes y consulta guardada | 422 entrada / 404 paciente / 409 ID reutilizado / 503 dependencia o guardado |
| `GET /patients/{id}/history` (Java) | 200, Markdown, revisión, registros y consultas | 404 paciente |
| `GET /patients/{id}/history.md` (Java) | 200, descarga Markdown | 404 paciente |
| `PUT /patients/{id}/history` (Java) | 200, informe actualizado | 409 revisión antigua / 422 inválido |
| `POST /patients/{id}/history/entries` (Java) | 201, informe con nuevo registro | 409 revisión antigua / 422 inválido |
| `POST /patients/{id}/consultations` (Java) | 201, consulta guardada; 200 si ya existía idéntica | 409 UUID reutilizado / 422 inválido |
| `GET /patients/{id}/consultations/{uuid}` (Java) | 200, consulta guardada | 404 ausente |
| `POST /clinical/proposals` (Python) | 200, propuestas editables y evidencia | 422 entrada / 404 paciente / 503 dependencia |
| `POST /clinical/patients/{id}/sync` (Python) | 200, índice sincronizado o retirado | 503 dependencia |

El Markdown reúne los registros confirmados y las consultas. `public.patient_diseases` guarda sus tres campos por UUID y `patient_id`; `public.medical_consultations` conserva las consultas y versiones completas del informe. `public.transaction_logs` guarda una fila por operación HTTP, con un único UUID `id` y el `patient_id` cuando corresponde. Los nombres están en inglés y `snake_case`. Qdrant mantiene el índice de búsqueda. [Uso y consultas SQL](GUIA.md#historia-clínica).

Editar los registros del Markdown requiere revisión vigente y confirmación; el historial de consultas conserva su texto original. Un 409 conserva el borrador: recarga la historia y revísalo antes de guardar. El navegador reutiliza `X-Execution-ID` si reintentas la misma consulta tras un fallo de conexión sin recargar la página, para no duplicarla.

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
