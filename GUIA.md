# Guía rápida

PowerShell 7, Python 3 y Docker Desktop. Todo desde `codigo/`. [Arranque y CRUD manual](README.md).

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

1. **Consultas médicas:** elige un paciente, describe la consulta o pregunta por sus antecedentes y pulsa **Comparar y guardar**. Abre cada fuente para leer el fragmento y su UUID. Al terminar aparece la confirmación de guardado y el enlace al informe.
2. **Pacientes:** agrega, busca o edita pacientes. Pulsa su nombre para abrir la historia; **Eliminar** pide confirmación y retira su archivo activo, conservando los respaldos SQL.
3. **API Python:** abre una operación, completa el ID o el JSON y pulsa **Ejecutar petición**.
4. **API Java:** lo mismo, pero contra Spring Boot. Los colores distinguen GET, POST, PUT y DELETE; el resultado muestra el código HTTP y el detalle del error si lo hay.

La tabla, el selector clínico y las dos APIs comparten `public.patients`. Cada alta crea su informe Markdown automáticamente. Los exploradores modifican datos reales de esta app local; usa un paciente temporal para practicar.

Para actualizar una instalación que ya está funcionando:

```powershell
docker compose up -d --build --no-deps python-api java-api
```

Recarga la pestaña al terminar o al cambiar de semana. Si sigues viendo la pantalla antigua sin las cuatro secciones, guarda lo que tengas escrito y pulsa **Ctrl+Shift+R**: una pestaña abierta puede conservar la interfaz anterior aunque el backend ya esté actualizado. En las copias semanales, sigue su `LEVANTAR.txt`.

## Historia clínica

Para verla: **Pacientes → nombre del paciente**. La primera tabla muestra registros confirmados: ID, enfermedad, tratamiento y medicamento. Debajo, **Consultas guardadas** muestra fecha, lo que escribiste y las dos respuestas de IA.

Para guardar una consulta: usa **Consultas médicas → Comparar y guardar**. Se guarda automáticamente el texto y las respuestas en el `.md` y en PostgreSQL. Los síntomas que escribes y la orientación del modelo no se convierten por eso en diagnósticos confirmados.

Para añadir datos: **Registros confirmados → Agregar registro → completar enfermedad, tratamiento y medicamento → Guardar registro → Confirmar y guardar**. Basta con un campo; deja vacío lo que no sepas. Usa **Editar** o **Eliminar** en la misma fila. Cada cambio actualiza la tabla SQL y el Markdown conservando el UUID.

Para partir de una nota: **Preparar desde una nota → escribir los hechos ficticios → Preparar con IA → revisar campos → Guardar este registro**. Puedes corregir la propuesta antes de confirmarla.

Para ver o bajar el archivo: **Ver archivo Markdown → Descargar .md**. Para editar los registros confirmados: **Editar Markdown → Guardar Markdown → Confirmar y guardar**. Conserva sus UUID y la sección **Consultas registradas**, que mantiene el historial original. Si aparece 409, pulsa **Actualizar historia**, compara tu borrador con la versión actual y confirma de nuevo.

El guardado actualiza el índice RAG. Si falla, el informe queda guardado: pulsa **Reintentar sincronización**. Renombrar o eliminar pacientes también sincroniza; el reintento no repite el cambio guardado.

Si al terminar el chat aparece **Falta actualizar el índice RAG**, la consulta ya quedó guardada: pulsa **Reintentar índice RAG**. No vuelve a generar ni a guardar la consulta. Si se cortó la conexión, reintenta el mismo texto con el mismo paciente sin recargar la página: el navegador conserva su UUID para evitar duplicarlo.

Los informes viven en `datos/historias/paciente-ID-nombre.md`, montado con escritura en ambas APIs. `public.patient_diseases` guarda los registros confirmados y los relaciona con `public.patients` mediante `patient_id`. `public.medical_consultations` conserva las consultas y versiones completas del Markdown. `public.transaction_logs` guarda un solo UUID `id` por operación, más `patient_id`, API, verbo, operación, código HTTP y cuerpos de entrada/salida. Conserva tanto la carpeta como el volumen PostgreSQL. Las consultas de uso modifican los Markdown locales; las semillas versionadas y las copias semanales se mantienen sin ese diario personal.

Para ver las últimas consultas guardadas:

```powershell
'SELECT id, patient_id, created_at, question, model FROM public.medical_consultations WHERE kind = ''consultation'' ORDER BY created_at DESC LIMIT 10;' | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Para ver las últimas transacciones de las APIs:

```powershell
'SELECT id, patient_id, service, method, operation, http_status, created_at FROM public.transaction_logs ORDER BY created_at DESC LIMIT 20;' | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

En los logs, `patient_id` queda vacío cuando la operación no corresponde a un paciente. Se conserva aunque borres ese paciente, para poder revisar lo que ocurrió. Los identificadores de cabecera sirven para trazas e idempotencia del chat; no añaden columnas UUID a `transaction_logs`.

En `medical_consultations`, `kind = 'consultation'` identifica una consulta; `snapshot` guarda una versión del informe y `deleted` respalda su última versión al borrar el paciente. `markdown_content` contiene el Markdown completo. Eliminar el paciente retira el archivo activo, pero conserva los respaldos y las transacciones.

Para leer el último respaldo del Markdown de Ana:

```powershell
'SELECT filename, revision, markdown_content FROM public.medical_consultations WHERE patient_id = 1 ORDER BY storage_order DESC LIMIT 1;' | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

El registro HTTP cubre las rutas de pacientes, chat y clínica, incluidos sus errores; omite las sondas y archivos de la página. Guarda hasta 128 KiB de cada cuerpo e indica cualquier recorte en `request_truncated` y `response_truncated`. No guarda las cabeceras. Si falla la escritura del log SQL, se registra el error en los logs de la API; no se deshace una operación de negocio ya completada.

## Pacientes compartidos

Para listar desde Python y Java:

```powershell
curl.exe -i http://localhost:8000/patients
curl.exe -i http://localhost:8080/patients
```

Para cargar la demo en una instalación nueva:

```powershell
docker compose exec -T python-api python inicializar_datos.py
```

La carga conserva los datos existentes. No repitas POST sobre los tres ejemplos: úsalo para pacientes nuevos. Las dos APIs crean el Markdown al dar de alta y mantienen la misma identidad.

Para ver los registros confirmados de Ana desde cualquiera de las APIs:

```powershell
curl.exe -i http://localhost:8000/patients/1/diseases
curl.exe -i http://localhost:8080/patients/1/diseases
```

Para ver la tabla clínica en PostgreSQL:

```powershell
'SELECT id, patient_id, disease, treatment, medication FROM public.patient_diseases ORDER BY patient_id, id;' | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Para practicar el CRUD de enfermedades, abre **API Python** o **API Java** y busca `/patients/{id}/diseases`. POST recibe los tres textos y devuelve un UUID. Copia ese UUID para GET, PUT o DELETE del registro. Las rutas siempre incluyen el ID del paciente.

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
docker compose exec postgres psql -U genai -d genai -c "SELECT count(*) AS patients FROM public.patients;"
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

Para cotejar el corpus inicial y sus cuatro búsquedas (tres informes, un registro por paciente y nueve puntos, antes de añadir o editar registros):

```powershell
Get-Content -Raw scripts/verificar_recuperacion.py | docker compose exec -T python-api python
```

## Chatbot en el navegador

Para descargar el modelo de chat, si falta:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull qwen3.5:4b-q4_K_M
```

**Ollama** es el servidor local; **Qwen 3.5 de 4B** es el modelo que responde (`qwen3.5:4b-q4_K_M`). Ambas ramas usan la misma pregunta y parámetros, con temperatura `0.2` y `think=false`.

La primera carga o una respuesta larga pueden demorar más. Espera la confirmación de guardado antes de enviar otra consulta.

Abre [el chatbot](http://localhost:8000). Elige Ana y pregunta «¿Qué enfermedad tiene Ana Demo?»; después «¿Cuál fue la última cirugía de Ana Demo?». RAG debe recuperar su reflujo gastroesofágico y citar la historia en la primera, y reconocer que falta información en la segunda.

Ana tiene un caso simulado de reflujo con omeprazol; Bruno, diabetes tipo 2 con metformina; Carla, rinitis alérgica por polen con cetirizina. Los planes, preguntas para probar y fuentes están en [Casos de prueba](datos/CASOS.md). Las dosis y algunos antecedentes se dejan sin registrar para comprobar que el RAG no los invente.

«Con RAG» comprueba la historia vigente del paciente, sincroniza su índice y busca hasta tres fragmentos del paciente. «Sin RAG» recibe solo la pregunta; ambas usan el mismo modelo y parámetros. Cada fuente muestra el archivo, UUID, sección y texto para cotejar la respuesta.

Puedes preguntar por datos registrados o describir síntomas de una consulta ficticia, incluso con una frase corta como `dolor de estómago`. Ambas ramas deben ofrecer posibles causas y explicar qué datos apoyarían cada una. Si faltan detalles, los sugieren al final sin bloquear la orientación. RAG separa los antecedentes del informe de esas posibilidades. No son diagnósticos confirmados ni recetas.

Para ajustar el prompt: abre `python-api/rag.py`. `SYMPTOM_GUIDANCE` contiene las reglas compartidas; `DIRECT_SYSTEM` y `RAG_SYSTEM`, las de cada rama. `build_rag_prompt` agrega la pregunta y los fragmentos del paciente. `python-api/orientation.py` valida y presenta las causas y condiciones como texto. El modelo y sus parámetros están en `python-api/app/llm.py`. Después de cambiar código Python:

```powershell
docker compose up -d --build --no-deps python-api
```

Si preguntas qué consta en la historia, RAG responde sólo con antecedentes respaldados. Cuando el dato no está registrado, lo reconoce; no completa el historial con una suposición.

Cada consulta terminada se añade al Markdown y a PostgreSQL con un UUID. Los registros confirmados de enfermedad, tratamiento y medicamento siguen siendo distintos: se guardan después de revisar sus campos. Las respuestas anteriores de IA no se reutilizan como hechos confirmados del paciente.

Las citas de antecedentes se comprueban contra los fragmentos recuperados. Si falta un dato del historial, se indica; la orientación de la consulta se presenta por separado. Una cita válida demuestra de dónde viene el texto, no la exactitud de cualquier interpretación del modelo: puedes cotejarla abriendo sus fuentes.

Para comprobar ambos casos del dataset inicial por API:

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

Si usas `capturar_loki.cjs`, pásale ese JSON recién generado: `node scripts/capturar_loki.cjs "ejecuciones/$ejecucion-loki.json"`. Necesita Playwright y Edge instalados.

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

Para compartir los mismos informes de Compose:

```powershell
.\scripts\montar_historias_minikube.ps1
```

Deja un proceso oculto de Minikube que mantiene la carpeta conectada. Si reinicias el equipo o detienes el perfil, usa después `reanudar_minikube.ps1`: comprueba y recupera el montaje por ti.

Para construir la imagen:

```powershell
docker build --tag genai-fastapi:s09-pacientes-compartidos-20261107 --progress=plain ./python-api
```

Para cargarla en el perfil:

```powershell
.\.local\bin\minikube.exe --profile=genai image load genai-fastapi:s09-pacientes-compartidos-20261107
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

Usa `192.168.49.10:5432` en la red `genai`; conserva la red original de PostgreSQL. El chart ya tiene esa IP.

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

Espera PostgreSQL, asegura su conexión directa y comparte `datos/historias` con las dos réplicas. Comprueba lectura, escritura y SQL antes de abrir los túneles. Si recuperó el montaje, renueva los pods para usarlo. El chat sigue en Compose, puerto 8000.

El CRUD de Minikube usa los mismos pacientes e informes que Compose. Si falta el montaje, el marcador impide arrancar la API o devuelve 503 en salud; ejecuta otra vez el comando de reanudación. Sus registros están en `.local/historias-mount-genai.*`.

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

Para comprobar un cambio de réplicas publicado, usa `verificar_gitops.py` con su SHA nuevo. Para consultar el estado actual bastan los comandos anteriores.

## Comprobar el entorno completo

Para revisar los ocho accesos, con Minikube y sus túneles abiertos:

```powershell
python scripts/verificar_componentes.py --output "ejecuciones/$ejecucion-componentes.json"
```

Usa `$ejecucion` del bloque de observabilidad. Si Loki aún arranca, espera y repite con un nombre nuevo.

Para comprobar la interfaz servida sin abrir el navegador:

```powershell
python -B scripts/verificar_assets.py
```

Para probar el CRUD compartido entre Python y Java:

```powershell
python -B scripts/verificar_backend_cruzado.py crud
```

Crea y retira sólo su paciente temporal; conserva sus logs y respaldos SQL. No edites pacientes durante la prueba. Los resultados quedan en `.local/verificaciones/`.

Para probar las reglas de conexión de Minikube sin iniciar ni detener contenedores:

```powershell
.\scripts\verificar_conexion_minikube.ps1
```

## Revisar calidad con SonarQube

Para levantar Sonar y analizar este proyecto, desde PowerShell 7:

```powershell
cd C:\Users\marco\Documents\CONKORD\SonarQube
.\sonar.ps1 iniciar
.\escanear.ps1
```

Abre [el resultado](http://localhost:9000/dashboard?id=genairui-formacion2026). El script analiza una copia y revoca su token al terminar. `SUCCESS` indica que terminó el análisis; el Quality Gate puede seguir en rojo por sus umbrales. La cobertura necesita un reporte: el 0 % mostrado aquí no significa que no existan pruebas.

Las correcciones y los avisos conservados están resumidos en [la revisión actual](evidencias/calidad-2026-11-12/LEEME.md). No cambies las reglas sólo para obtener un resultado verde.
