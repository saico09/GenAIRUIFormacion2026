# HDU-035 · Chatbot con StateGraph · 28/10/2026

El POST `/chat` ejecuta la rama directa y después invoca el grafo para RAG. Conserva `direct_answer`, `rag_answer` y `sources`, la misma pregunta, `llama3.2:3b`, temperatura 0, contexto 2048 y salida máxima de 256 tokens. Se retiró `answer_rag`, que ya no tenía llamadas; `rag.py` mantiene la construcción del prompt. La prueba HDU-034 por consola se conserva como evidencia del paso anterior.

Se probaron desde la página los casos 0 y 3 de `datos/preguntas.json`, ambos con `patient_id=1`. El verificador capturó el header X-Request-ID, comprobó ambos POST 200 y cotejó las respuestas y fuentes visibles con el JSON. [Resultados completos](035-resultados.json).

## Enfermedad de Ana

Pregunta: **¿Qué enfermedad tiene Ana Demo?**

Request_id: `1d6ca156-4d3d-4c94-ace9-ea7f223781fd`.

Respuesta directa:

> Lo siento, pero no tengo información sobre una persona llamada Ana Demo o su enfermedad. Es posible que la persona en cuestión sea una figura pública o un personaje de ficción que no tengo información sobre. Si puedes proporcionar más contexto o detalles, estaré encantado de tratar de ayudarte.

Respuesta RAG:

```text
Respuesta: Enfermedad Alfa.
Fuente: [paciente-1.md/Enfermedad]
```

Fuentes recuperadas: Enfermedad y Tratamiento de `paciente-1.md`, ambas con patient_id 1. La primera respalda Alfa. [Captura inspeccionada](035-caso-1.png).

## Cirugía ausente

Pregunta: **¿Cuál fue la última cirugía de Ana Demo?**

Request_id: `8ed7120d-2024-46ee-94ad-79131d9f376d`.

Respuesta directa:

> Lo siento, pero no tengo información sobre una persona llamada Ana Demo o su historial de cirugías. Es posible que la información que buscas sea confidencial o no esté disponible públicamente. Si puedes proporcionar más contexto o detalles sobre quién es Ana Demo y qué tipo de cirugías está hablando, estaré encantado de tratar de ayudarte.

Respuesta RAG:

```text
No hay información suficiente.
```

Fuentes recuperadas: Enfermedad y Tratamiento de `paciente-1.md`, ambas con patient_id 1. Ninguna contiene una cirugía; recuperarlas no demuestra ese dato. [Captura inspeccionada](035-caso-2.png).

## Recorrido comprobado

Para cada id, [035-correlacion.json](035-correlacion.json) conserva cuatro eventos `rag_node` en orden: retrieval, prompt, llamada_llm y respuesta. También guarda dos eventos LLM y un HTTP 200. El verificador cotejó el modelo compartido, pregunta exacta, fragmentos incluidos en el prompt RAG y respuestas iguales a las mostradas en el navegador. Cada caso tiene siete eventos con su mismo request_id.

Para repetir desde `codigo/`, con los servicios y Ollama encendidos:

indicar dónde está Playwright:
```powershell
$env:NODE_PATH = 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
```

elegir la carpeta:
```powershell
$env:EVIDENCE_DIR = 'evidencias/s08'
```

elegir el prefijo (reemplaza los resultados 035 si lo repites):
```powershell
$env:EVIDENCE_PREFIX = '035'
```

ejecutar ambos casos en Edge:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts/verificar_chat_ui.cjs --demo
```

comprobar la correlación enseguida (consulta la última hora de Loki):
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_grafo_logs.py evidencias/s08/035-resultados.json --output evidencias/s08/035-correlacion.json
```

Las dos capturas se inspeccionaron. Esta comprobación técnica no acredita explicación personal de Marco, revisión de Rui ni horas de formación realizadas.
