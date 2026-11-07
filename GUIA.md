# Guía rápida

PowerShell 7, Python 3 y Docker Desktop. Todo desde `codigo/`. [Arranque y CRUD manual](README.md) · [Demo S5](evidencias/S05-guion.md) · [Demo final](evidencias/s10/guion.md).

Para entrar:

```powershell
Set-Location 'C:\Users\marco\Documents\CONKORD\GenAIRUIFormacion2026\codigo'
```

Para corregir tildes de la consola, si se ven raras:

```powershell
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
```

## Arranque

Para levantar los contenedores:

```powershell
docker compose up -d --build
```

Para esperar las APIs:

```powershell
.\scripts\esperar_apis.ps1
```

Para ver los servicios:

```powershell
docker compose ps
```

Para iniciar Ollama:

```powershell
.\scripts\iniciar_ollama.ps1
```

## Usar la página

Abre [localhost:8000](http://localhost:8000). Arriba tienes cuatro secciones:

1. **Consultas médicas:** elige un paciente Java, escribe la pregunta y pulsa **Comparar respuestas**. Abre cada fuente para leer el fragmento y su UUID de registro.
2. **Pacientes:** agrega, busca o edita pacientes. Pulsa su nombre para abrir la historia; **Eliminar** pide confirmación y también elimina su informe.
3. **API Python:** abre una operación, completa el ID o el JSON y pulsa **Ejecutar petición**.
4. **API Java:** lo mismo, pero contra Spring Boot. Los colores distinguen GET, POST, PUT y DELETE; el resultado muestra el código HTTP y el detalle del error si lo hay.

La tabla y el selector clínico comparten los pacientes Java. El CRUD Python conserva su tabla independiente. Los exploradores modifican datos reales de esta app local; usa un paciente temporal para practicar.

Para actualizar una instalación que ya está funcionando:

```powershell
docker compose up -d --build --no-deps python-api java-api
```

Recarga la página al terminar. En las copias semanales, usa la dirección de su `LEVANTAR.txt`.

## Historia clínica

Para verla: **Pacientes → nombre del paciente**. La tabla muestra ID del registro, enfermedad, tratamiento y medicamento; un guion indica que no hay dato.

Para guardar una consulta: **Nueva consulta → escribir la nota ficticia → Preparar con IA**. Revisa los tres campos y el texto de origen, corrige lo necesario y pulsa **Guardar este registro → Confirmar y guardar**. Si la IA no encuentra hechos o no está disponible, usa **Crear registro manual**. No completa diagnósticos ni datos ausentes.

Para ver o bajar el archivo: **Ver archivo Markdown → Descargar .md**. Para editarlo: **Editar Markdown → Guardar Markdown → Confirmar y guardar**. Conserva los UUID; las altas se hacen desde **Nueva consulta**. Si aparece 409, pulsa **Actualizar historia**, compara tu borrador con la versión actual y confirma de nuevo.

El guardado actualiza el índice RAG. Si falla, el informe queda guardado: pulsa **Reintentar sincronización**. Renombrar o eliminar pacientes también sincroniza; el reintento no repite el cambio en Java.

Para aprovechar una pregunta del chat: **Preparar registro** la lleva como borrador a **Nueva consulta**. Preguntar, preparar y revisar no guardan nada; la respuesta RAG nunca se archiva automáticamente.

Los informes viven en `datos/historias/paciente-ID-nombre.md`, montado con escritura en Java por Compose. El `.md` es la fuente clínica; PostgreSQL guarda nombre, nacimiento y correo, y Qdrant indexa sus fragmentos. Conserva esa carpeta al reiniciar.

## Pacientes Python

Para consultar los pacientes antes de cargar datos:

```powershell
curl.exe -i http://localhost:8000/patients
```

Para cargar los tres ficticios **solo si faltan**:

```powershell
(Get-Content datos/pacientes.json -Raw | ConvertFrom-Json) | ForEach-Object { Invoke-RestMethod -Method Post -Uri http://localhost:8000/patients -ContentType 'application/json' -Body ($_ | ConvertTo-Json) }
```

Ojo: repetir esta carga duplica pacientes. En este equipo ya estaban cargados.

## Pacientes Java

Para consultar Java:

```powershell
curl.exe -i http://localhost:8080/patients
```

Para cargar los ficticios **solo si faltan en Java**:

```powershell
(Get-Content datos/pacientes.json -Raw | ConvertFrom-Json) | ForEach-Object { Invoke-RestMethod -Method Post -Uri http://localhost:8080/patients -ContentType 'application/json' -Body ($_ | ConvertTo-Json) }
```

Repetirlo también duplica filas. Los ids de Java y Python son independientes.

## Comprobar el CRUD

Para probar Python:

```powershell
Get-Content -Raw scripts/verificar_crud.py | docker compose exec -T python-api python - --base-url http://localhost:8000
```

Para probar Java:

```powershell
Get-Content -Raw scripts/verificar_crud.py | docker compose exec -T python-api python - --base-url http://java-api:8080
```

Cada prueba borra solo su temporal y comprueba 404/422 sin cambiar filas previas. No edites pacientes mientras corre.

## Comprobar persistencia

Para reiniciar PostgreSQL y Python y comparar los datos:

```powershell
.\scripts\verificar_persistencia.ps1
```

Para hacerlo con Java:

```powershell
.\scripts\verificar_persistencia.ps1 -Servicio java-api
```

Necesita Ana Demo original. Interrumpe brevemente la base compartida; conserva el volumen.

## Postgres

Para entrar a SQL (salir con `\q`):

```powershell
docker compose exec postgres psql -U genai -d genai
```

Para contar filas sin mostrar datos personales:

```powershell
docker compose exec postgres psql -U genai -d genai -c "SELECT 'python' AS api, count(*) FROM public.patients UNION ALL SELECT 'java', count(*) FROM java.patients;"
```

DBeaver: `localhost:5432`, base `genai`, usuario/clave de `.env`. Minikube usa la conexión directa por la red Docker `genai`.

## Embeddings y Qdrant

Para descargar embeddings, si falta el modelo:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull nomic-embed-text
```

Para cargar o actualizar los informes confirmados sin duplicar fragmentos:

```powershell
docker compose exec -T python-api python ingestar.py
```

Para buscar solo dentro de Ana:

```powershell
docker compose exec -T python-api python buscar.py 1 "¿Qué enfermedad tiene Ana Demo?"
```

Para cotejar documentos, puntos y cuatro búsquedas:

```powershell
Get-Content -Raw scripts/verificar_recuperacion.py | docker compose exec -T python-api python
```

## Chatbot en el navegador

Para descargar el modelo de chat, si falta:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull llama3.2:3b
```

Abre [el chatbot](http://localhost:8000). Elige Ana y pregunta «¿Qué enfermedad tiene Ana Demo?»; después «¿Cuál fue la última cirugía de Ana Demo?». RAG debe usar Alfa y su fuente en la primera y reconocer que falta información en la segunda.

«Con RAG» comprueba la historia vigente de Java, sincroniza su índice y busca hasta tres fragmentos del paciente. «Sin RAG» recibe solo la pregunta; ambas usan el mismo modelo y parámetros. Cada fuente muestra el archivo, UUID, sección y texto para cotejar la respuesta.

Pregunta por enfermedades, tratamientos o medicamentos registrados: el chat no infiere consejos ni diagnósticos nuevos a partir de síntomas.

Cada registro agrupa enfermedad, tratamiento y medicamento bajo un UUID. Puedes tener varios registros por paciente; sólo se usa lo que consta en su informe. Preguntar no modifica esos archivos. Cada pregunta es independiente: los logs no funcionan como memoria del chat.

«Con RAG» selecciona citas literales: antes de mostrarlas, el código comprueba que el texto y la fuente pertenecen a los fragmentos recuperados. Si faltan datos o esa comprobación falla, responde «No hay información suficiente». Esto verifica la procedencia, no garantiza que el modelo haya interpretado bien la pregunta; coteja la respuesta con las fuentes.

La revisión del 07/11 detectó respuestas sin respaldo fuera de los casos preparados. [Experimentos anteriores](evidencias/revision-rag-2026-11-07/LEEME.md). El registro asistido fue solicitado por Marco; no añade requisitos de Rui.

Para comprobar ambos casos por API:

```powershell
Get-Content -Raw scripts/verificar_chat.py | docker compose exec -T python-api python
```

## Ejecutar el grafo

Para ver el recorrido retrieval → prompt → llamada_llm → respuesta:

```powershell
docker compose exec -T python-api python grafo.py 1 "¿Qué enfermedad tiene Ana Demo?" --output /tmp/grafo.json
```

Para leer su estado final:

```powershell
docker compose exec -T python-api cat /tmp/grafo.json
```

## Métricas y Grafana

Para probar los contadores Python:

```powershell
Get-Content -Raw scripts/verificar_metricas.py | docker compose exec -T python-api python -
```

Para probar Java:

```powershell
Get-Content -Raw scripts/verificar_metricas.py | docker compose exec -T python-api python - --service springboot
```

[Prometheus targets](http://localhost:9090/targets) · [Dashboard](http://localhost:3000/d/genai-apis/apis-genai). Grafana: `admin`; clave local en `GRAFANA_ADMIN_PASSWORD` de `.env`.

Para consultar esa clave solo en tu terminal:

```powershell
Get-Content .env | Select-String '^GRAFANA_ADMIN_PASSWORD='
```

## Repetir la observabilidad

Para crear un nombre nuevo de ejecución:

```powershell
$ejecucion = [guid]::NewGuid().ToString('N')
```

Para generar 50 GET y llenar los paneles (unos dos minutos):

```powershell
python scripts/generar_trafico.py --output "ejecuciones/$ejecucion-trafico.json"
```

req/s es tráfico; error % es la proporción 4xx/5xx; p95 es latencia agregada del servidor, no el tiempo de un chat concreto.

## Logs

Para comprobar los eventos HTTP sin sobrescribir evidencia:

```powershell
python scripts/verificar_logs.py
```

Para ver logs recientes:

```powershell
docker compose logs --no-log-prefix --since 2m python-api java-api
```

Para generar peticiones y encontrarlas en Loki:

```powershell
python scripts/verificar_loki.py --output "ejecuciones/$ejecucion-loki.json"
```

Para seguir las dos llamadas del LLM:

```powershell
python scripts/verificar_llm_logs.py --prefix demo --output "ejecuciones/$ejecucion-llm.json"
```

Usa primero `$ejecucion` del bloque anterior. En Grafana → Explore → Loki, copia el `request_id` del JSON:

```logql
{service="fastapi"} | json | request_id="ID_DE_TU_PRUEBA"
```

Para Java cambia `fastapi` por `springboot`. Si Loki dice `not ready`, espera 30 segundos y repite. Los prompts contienen datos: usa los ficticios.

## Trazas en Phoenix

Para crear una pregunta y comprobar cinco spans y sus logs:

```powershell
python scripts/verificar_traza.py --prefix demo --output "ejecuciones/$ejecucion-traza.json"
```

Usa `$ejecucion` del bloque de observabilidad. Abre la `url` del JSON en [Phoenix](http://localhost:6006): raíz `rag` y cuatro nodos, con el mismo `request_id` de Loki.

<a id="preparar-minikube"></a>

## Preparar Minikube por primera vez

Para instalar las herramientas locales:

```powershell
.\scripts\instalar_gitops.ps1
```

Para crear el perfil (2 CPU y 3072 MiB):

```powershell
.\.local\bin\minikube.exe start --profile=genai --driver=docker --cpus=2 --memory=3072 --kubernetes-version=v1.36.6 --keep-context --wait=all --wait-timeout=6m
```

Para construir la imagen:

```powershell
docker build --tag genai-fastapi:s09-reanudacion-20261103 --progress=plain ./python-api
```

Para cargarla en el perfil:

```powershell
.\.local\bin\minikube.exe --profile=genai image load genai-fastapi:s09-reanudacion-20261103
```

<a id="chart-y-conexión-a-postgres"></a>

Para esperar PostgreSQL antes del primer despliegue:

```powershell
docker compose up -d --wait --wait-timeout 120 postgres
```

Para conectarlo directamente al perfil, antes de aplicar el chart:

```powershell
.\scripts\conectar_postgres_minikube.ps1
```

Usa `192.168.49.10:5432` en la red `genai`; conserva la red original de PostgreSQL. El chart ya tiene esa IP. La [prueba SQL antigua](evidencias/s09/040-conectividad.md) conserva el host usado en octubre.

Para preparar el Secret desde `.env`:

```powershell
.\scripts\crear_secret_postgres.ps1
```

Para validar el chart:

```powershell
.\.local\bin\helm.exe lint deploy/helm/fastapi
```

<a id="preparar-argo-cd"></a>

Para instalar Argo CD:

```powershell
.\scripts\instalar_argocd.ps1
```

Para conectar el repositorio:

```powershell
.\.local\bin\kubectl.exe --context=genai apply -f deploy/argocd/repositorio.yaml
```

Para crear la Application:

```powershell
.\.local\bin\kubectl.exe --context=genai apply -f deploy/argocd/fastapi.yaml
```

Argo sigue `main`: revisa los cambios de `deploy/` antes de publicarlos. Solo se despliega el CRUD FastAPI.

## FastAPI desde Git

Para reanudar el perfil ya creado y abrir sus accesos:

```powershell
.\scripts\reanudar_minikube.ps1
```

Espera PostgreSQL, asegura su conexión directa, comprueba SQL desde Minikube y las réplicas Ready; después abre los túneles. Solo levanta el CRUD de este perfil; el chat sigue en Compose, puerto 8000.

Necesita que Docker Desktop responda. La ruta directa evita el puerto publicado de Windows; no repara un backend de Docker bloqueado.

Para abrir o recuperar Argo CD:

```powershell
.\scripts\abrir_argocd.ps1
```

Para leer su clave inicial solo en tu terminal (usuario `admin`):

```powershell
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((.\.local\bin\kubectl.exe --context=genai -n argocd get secret argocd-initial-admin-secret -o 'jsonpath={.data.password}')))
```

Para abrir o recuperar el CRUD:

```powershell
.\scripts\abrir_fastapi_minikube.ps1
```

Para consultar Ana:

```powershell
curl.exe -i http://localhost:8002/patients/1
```

<a id="dos-réplicas-y-reposición"></a>

Para ver los pods actuales:

```powershell
.\.local\bin\kubectl.exe --context=genai -n genai get pods -l app=fastapi -o wide
```

Para ver la sincronización actual:

```powershell
.\.local\bin\kubectl.exe --context=genai -n argocd get application fastapi -o 'custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,REVISION:.status.sync.revision,OPERACION:.status.operationState.phase'
```

El chat sigue en 8000. Si reemplazas un pod, vuelve a ejecutar el helper del túnel antes del GET.

## Guion final

Para repetir la demo: [guion](evidencias/s10/guion.md). Para volver de dos a una réplica por Git: [preparación](evidencias/s10/gitops-preparacion.md#volver-a-una-réplica-para-otra-demo).

Usa `verificar_gitops.py` con el SHA nuevo justo después de cambiar réplicas; los SHA antiguos son evidencia histórica. Para una consulta normal usa los comandos de estado anteriores. Si reaparece el error de reloj de Argo, conserva el fallo y sigue el [diagnóstico](evidencias/s10/046-reloj.md); no cambies relojes ni status.

<a id="retomar-después-del-receso"></a>

Para retomar tras una pausa, sigue [Arrancar](README.md#arrancar), consulta Ana y repite la prueba de chat. El receso previsto sigue siendo 21/12–01/01, sin tareas.

## Comprobar el entorno completo

Para revisar los ocho accesos, con Minikube y sus túneles abiertos:

```powershell
python scripts/verificar_componentes.py --output "ejecuciones/$ejecucion-componentes.json"
```

Usa `$ejecucion` del bloque de observabilidad. Si Loki aún arranca, espera y repite con un nombre nuevo.

La [guía extensa anterior](evidencias/revision-claude/documentacion-original/GUIA.md) queda archivada; sus rutas relativas y resultados corresponden al documento original.
