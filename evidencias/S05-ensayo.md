# HDU-023 · Ensayo del recorrido · 28/10/2026

Se recorrieron los pasos permitidos de [S05-guion.md](S05-guion.md), desde el arranque del entorno existente hasta el chatbot. El ciclo completo de detener todo Compose y arrancarlo desde detenido sigue **NO EJECUTADO** por el rechazo automático previo de la parada de Qdrant. No se intentó esa parada ni una alternativa; Qdrant permaneció `Running` durante los dos comandos `up` de este ensayo.

El primer intento encontró una diferencia real: `docker compose up -d --build` devolvió los contenedores como `Started`, pero el `curl.exe -i http://localhost:8000/health` inmediato falló con **código 52, `Empty reply from server`**. La API todavía estaba iniciándose. Se creó [esperar_apis.ps1](../scripts/esperar_apis.ps1): espera HTTP 200 de ambas APIs, con límite global de 90 segundos, timeout de 2 segundos por conexión, un segundo entre intentos y error explícito si se agota el plazo.

Se repitió el arranque con la espera y se siguieron los comandos originales:

```powershell
docker compose up -d --build
.\scripts\esperar_apis.ps1
.\scripts\iniciar_ollama.ps1
curl.exe -i http://localhost:8000/health
curl.exe -i http://localhost:8080/health
```

La repetición terminó correctamente. [README](../README.md), [GUIA](../GUIA.md) y [guion](S05-guion.md) ya incluyen la espera después de `up`. Se corrigió la comprobación de disponibilidad, sin cambiar la lógica de pacientes ni RAG.

| Paso del guion | Resultado del ensayo | Evidencia |
|---|---|---|
| 1. Arranque sobre entorno existente | `up` código 0; espera confirmó ambas APIs; Ollama 0.40.12 disponible; health 200/200 | [arranque repetido](S05/023-compose-repetido.txt), [espera](S05/023-espera.txt), [Ollama](S05/023-ollama.txt), [health Python](S05/023-health-python.txt), [health Java](S05/023-health-java.txt) |
| 1. Ana y colección | GET Ana 200 en ambas APIs, con ID 1, nombre, fecha y email originales; Qdrant 9 puntos | [Ana Python](S05/023-ana-python.txt), [Ana Java](S05/023-ana-java.txt), [conteo](S05/023-conteo.json) |
| 2. CRUD Python | 201/200/200/200/204/404; temporal ID 13 eliminado; 28 entradas inválidas → 422; cuatro filas previas conservadas | [salida](S05/023-crud-python.txt) |
| 3. CRUD Java | Mismos códigos; temporal ID 11 eliminado; 28 entradas inválidas → 422; tres filas previas conservadas | [salida](S05/023-crud-java.txt) |
| 4. Reinicio PostgreSQL + Python | Cuatro filas conservadas, Ana ID 1 con sus cuatro campos originales | [persistencia Python](S05/023-persistencia-python.txt) |
| 4. Reinicio PostgreSQL + Java | Tres filas conservadas, Ana ID 1 con sus cuatro campos originales | [persistencia Java](S05/023-persistencia-java.txt) |
| 5. Búsqueda enfermedad de Ana | Dos fragmentos del ID 1; Enfermedad Alfa primero, con archivo y sección correctos | [respuesta](S05/023-busqueda-enfermedad.json) |
| 5. Búsqueda cirugía de Ana | Dos fragmentos del ID 1, Enfermedad y Tratamiento; ninguno contiene cirugía | [respuesta](S05/023-busqueda-cirugia.json) |
| 6. HTML, casos del guion y dataset completo | Cuatro HTTP 200: Alfa/Beta/Gamma con cita correcta; cirugía sin información | [respuestas completas](S05/023-resultados.json) |

Los CRUD y los dos verificadores de persistencia se ejecutaron secuencialmente como indica el guion. Los reinicios tocaron PostgreSQL y la API correspondiente, sin borrar volúmenes. Las comparaciones de las filas se hicieron en memoria sin imprimir el registro adicional del usuario.

Para la comprobación de HTML se usó el modo `--dataset` en lugar del modo abreviado `--demo`: incluye las dos preguntas de Ana del guion y también repite Bruno y Carla. Se guardó con prefijo `023`, sin sobrescribir los ensayos anteriores:

```powershell
$env:NODE_PATH = 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:EVIDENCE_DIR = (Join-Path $PWD 'evidencias\S05')
$env:EVIDENCE_PREFIX = '023'
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts\verificar_chat_ui.cjs --dataset
```

Resultado: código 0. Las capturas [Ana](S05/023-caso-1.png), [Bruno](S05/023-caso-2.png), [Carla](S05/023-caso-3.png) y [cirugía](S05/023-caso-4.png) se inspeccionaron: dos columnas legibles y fuentes del paciente correcto. RAG devolvió Enfermedad Alfa, Tratamiento Beta y Medicamento Gamma con las citas de sus secciones; para cirugía, `No hay información suficiente.`. Las respuestas directas se conservan completas y reconocen que no tienen información.

El verificador confirmó que el POST contiene la pregunta exacta y que las respuestas visibles coinciden con el JSON. [Configuración leída dentro de Python](S05/023-parametros.json): ambas ramas reutilizan `app.llm.llamar_llm`, modelo `llama3.2:3b`, temperatura 0 y timeout 120 segundos por llamada; la función mantiene contexto 2048 y máximo 256 tokens.

Tres frases de apoyo sobre API → PostgreSQL:

1. En Python, [schemas.py](../python-api/app/schemas.py) valida el JSON y [main.py](../python-api/app/main.py) entrega los campos válidos al modelo y la sesión SQLAlchemy.
2. En Java, [PatientController.java](../java-api/src/main/java/com/conkord/genai/PatientController.java) usa el repositorio JPA; ambas APIs escriben en PostgreSQL, en tablas separadas `public.patients` y `java.patients`.
3. El volumen `pgdata` de [Compose](../compose.yml) conserva los archivos de la base cuando se reinicia un contenedor; el [verificador de persistencia](../scripts/verificar_persistencia.ps1) compara los datos antes y después.

Tres frases de apoyo sobre documento → embedding → Qdrant → prompt → LLM:

1. [ingestar.py](../python-api/ingestar.py) separa los Markdown y usa [knowledge.py](../python-api/app/knowledge.py) para convertir cada sección en un vector y guardarlo con su archivo, sección y paciente en Qdrant.
2. [buscar.py](../python-api/buscar.py) representa la pregunta con el mismo modelo de embeddings y recupera hasta dos fragmentos filtrados por `patient_id`.
3. [rag.py](../python-api/rag.py) añade esos textos y fuentes al prompt, y [llm.py](../python-api/app/llm.py) consulta el mismo modelo que la rama directa; la instrucción pide citar el dato o reconocer su ausencia, pero no convierte la similitud en certeza.

Estas frases son material de apoyo, no una explicación ya realizada por Marco. El fallo de disponibilidad inicial quedó corregido y repetido con éxito; no quedaron otros fallos funcionales de los pasos ejecutados. Siguen pendientes el ciclo completo desde detenido, comprensión personal y revisión de Rui. No se acredita una sesión ni valoración recibida.
