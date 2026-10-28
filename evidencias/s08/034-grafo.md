# HDU-034 · RAG con cuatro nodos

Comprobado el 28/10/2026 con datos sintéticos. El grafo quedó disponible en `python-api/grafo.py`; durante esta HDU se ejecutó por consola, antes de integrarlo al endpoint en la HDU-035.

El estado guarda `pregunta`, `patient_id`, `request_id`, `fragmentos`, `prompt` y `respuesta`. Reutiliza `search_fragments`, `build_rag_prompt` y `llamar_llm`, con el mismo modelo `llama3.2:3b`. La llamada LLM recibe el `request_id` mediante el contexto existente; el último nodo devuelve su respuesta sin modificarla.

```text
START → retrieval → prompt → llamada_llm → respuesta → END
```

Para reproducir desde `codigo/`:

```powershell
docker compose up -d --build --no-deps python-api
docker compose exec -T python-api pip check
$caso = (Get-Content datos/preguntas.json -Raw | ConvertFrom-Json)[0]
$requestId = 'hdu034-' + [guid]::NewGuid().ToString('N')
docker compose exec -T python-api python grafo.py $caso.patient_id $caso.question --request-id $requestId --output /tmp/grafo.json
docker compose cp python-api:/tmp/grafo.json evidencias/s08/grafo.json
```

| Comprobación | Resultado real |
|---|---|
| Dependencia nueva | LangGraph 1.2.18, instalado en Python 3.15.2 |
| Compilación del grafo | Cinco enlaces esperados, incluidos START y END; los nombres de nodos `prompt` y `respuesta` funcionan con los campos homónimos |
| Pregunta del dataset | `¿Qué enfermedad tiene Ana Demo?`, caso 0, `patient_id=1` |
| Recuperación | Dos fragmentos de `paciente-1.md`, ambos con `patient_id=1` |
| Prompt | Conserva la pregunta exacta e incluye los dos fragmentos recuperados |
| Respuesta real | `Respuesta: Enfermedad Alfa.` y `Fuente: [paciente-1.md/Enfermedad]` |
| Correlación | Un evento `llm`, rama `rag`, con el mismo ID, prompt y respuesta que el estado final |
| Dependencias y API | `pip check` correcto y `/health` HTTP 200 |

El primer build falló porque `zstandard 0.25.0`, requerido por `langsmith 0.14.14`, no ofrece una rueda Linux CPython 3.15 y no había compilador. Se resolvió con un Dockerfile de dos etapas: construye las ruedas en la primera y las instala en el runtime. También se compiló PyYAML 6.0.3. Se verificaron los imports y una compresión/descompresión con zstandard; la imagen final no contiene `gcc` ni el directorio `/wheels`. Las versiones y enlaces del grafo están en [034-runtime.json](034-runtime.json).

Evidencia principal: [grafo.json](grafo.json), [validación](034-validacion.json), [evento LLM](034-ejecucion.txt) y [pip check](034-pip-check.txt). La invocación preliminar `¿Cuál es el diagnóstico de Ana?` se conserva únicamente como [ensayo](034-ensayo.json); el archivo principal usa el texto exacto del dataset.

Quedan pendientes la explicación de Marco y la revisión de Rui; estas pruebas no acreditan horas de formación ni una revisión recibida.
