# HDU-022 · Guion de la demo · 28/10/2026

Todo desde `codigo/`, en PowerShell, con Docker Desktop abierto. Usa este equipo ya preparado: Ana, Bruno y Carla tienen ids Python 1, 2 y 3; Ana también tiene id 1 en Java. Los modelos y las nueve secciones ya están cargados. Conserva esos pacientes: los verificadores crean y eliminan solo su propio **Test Demo**.

Este guion reúne comandos comprobados en [S05-arranque](S05-arranque.md), [S05-pendientes](S05-pendientes.md), [S01](S01.md), [S02](S02.md) y [S03](S03.md). El [ensayo HDU-023](S05-ensayo.md) recorrió los pasos permitidos y corrigió la espera inicial; la [preparación HDU-024](S05-validacion.md) pasó también. Todavía no se acredita una demo con Rui ni explicación personal.

**Pendiente concreto:** el ciclo completo de detener todo Compose y arrancarlo desde detenido está **NO EJECUTADO**. Una revisión automática previa rechazó detener Qdrant (`blocked by policy`). Aquí no se repite esa parada ni se propone otra vía. El arranque sobre el entorno existente y los reinicios de PostgreSQL/APIs son comprobaciones distintas; la recreación automática de Qdrant en HDU-020 conservó nueve puntos, pero no completa ese ciclo.

## 1. Arranque y datos disponibles

levantar o actualizar el entorno existente:
```powershell
docker compose up -d --build
```

esperar a que las dos apis acepten peticiones (plazo máximo de 90 segundos):
```powershell
.\scripts\esperar_apis.ps1
```

Compose puede terminar antes que el arranque de las APIs. Este paso se añadió tras observar `Empty reply from server` en el primer intento de HDU-023 y se repitió correctamente: [espera comprobada](S05/023-espera.txt). El script falla con un mensaje si vence el plazo.

iniciar o reutilizar Ollama en Windows:
```powershell
.\scripts\iniciar_ollama.ps1
```

comprobar Python (200 y `status: ok`):
```powershell
curl.exe -i http://localhost:8000/health
```

comprobar Java (200 y `status: ok`):
```powershell
curl.exe -i http://localhost:8080/health
```

consultar Ana en Python (200; id 1, Ana Demo, 1990-01-10, ana@example.com):
```powershell
curl.exe -i http://localhost:8000/patients/1
```

consultar Ana en Java (200; los mismos cuatro campos):
```powershell
curl.exe -i http://localhost:8080/patients/1
```

contar los puntos de historias (200; `result.count` igual a 9):
```powershell
Invoke-RestMethod http://127.0.0.1:6333/collections/historias/points/count -Method Post -ContentType application/json -Body '{"exact":true}'
```

Código: [Compose](../compose.yml), [espera de APIs](../scripts/esperar_apis.ps1), [inicio de Ollama](../scripts/iniciar_ollama.ps1), [endpoints Python](../python-api/app/main.py) y [controlador Java](../java-api/src/main/java/com/conkord/genai/PatientController.java). Resultado real: [estado de HDU-020](S05/020-estado.json).

## 2. CRUD Python con su temporal

crear Test Demo, listar, consultar, editar, borrar y comprobar el borrado:
```powershell
Get-Content -Raw scripts\verificar_crud.py | docker compose exec -T python-api python - --base-url http://localhost:8000
```

El script guarda el id generado, cambia sus tres campos a los datos de Test Editado y elimina ese mismo id. No usa un id fijo para editar o borrar. Esperado:

| Operación | HTTP |
|---|---|
| Crear | 201 |
| Listar / consultar / editar | 200 / 200 / 200 |
| Borrar | 204, cuerpo vacío |
| Consultar el borrado | 404 |
| Consultar, editar o borrar el id ausente 999999 | 404 |
| 14 entradas inválidas en POST y PUT | 28 respuestas 422 |

Debe terminar con código 0 y las filas previas intactas: cuatro en este equipo. Código: [verificador](../scripts/verificar_crud.py), [validación](../python-api/app/schemas.py), [endpoints](../python-api/app/main.py), [modelo](../python-api/app/models.py) y [conexión](../python-api/app/db.py). Resultado real: [CRUD Python de HDU-021](S05/021-crud-python.txt). Los comandos individuales también están en la [guía](../GUIA.md#pacientes-python).

## 3. CRUD Java con otro temporal

repetir la misma secuencia y limpiar su Test Demo:
```powershell
Get-Content -Raw scripts\verificar_crud.py | docker compose exec -T python-api python - --base-url http://java-api:8080
```

Espera los mismos códigos de la tabla anterior y las tres filas originales intactas. `java-api:8080` es el nombre dentro de Docker; desde Windows es `localhost:8080`. Las tablas están separadas: `public.patients` para Python y `java.patients` para Java.

Código: [controlador](../java-api/src/main/java/com/conkord/genai/PatientController.java), [entrada validada](../java-api/src/main/java/com/conkord/genai/PatientRequest.java) y [verificador común](../scripts/verificar_crud.py). Resultado real: [CRUD Java de HDU-021](S05/021-crud-java.txt). Comandos individuales en la [guía](../GUIA.md#pacientes-java).

## 4. Reinicio sin borrar volúmenes

reiniciar PostgreSQL y Python y comparar los datos antes/después:
```powershell
.\scripts\verificar_persistencia.ps1
```

reiniciar PostgreSQL y Java y comparar los datos antes/después:
```powershell
.\scripts\verificar_persistencia.ps1 -Servicio java-api
```

Esperado: `OK`, cuatro filas Python y tres Java conservadas, Ana id 1 con sus cuatro campos originales. Cada script espera a que PostgreSQL y la API vuelvan a responder. La base se interrumpe brevemente para ambas APIs. No se borra `pgdata` ni `qdrant_data`; estos pasos no reinician Qdrant.

Código: [script de persistencia](../scripts/verificar_persistencia.ps1) y [volúmenes de Compose](../compose.yml). Evidencias previas: [HDU-004 en S01](S01.md) y [HDU-009 en S02](S02.md). El ciclo completo de detener todos los servicios continúa pendiente por el motivo indicado al comienzo.

## 5. Búsqueda en Qdrant

buscar los dos fragmentos de Ana más cercanos a la pregunta de enfermedad:
```powershell
docker compose exec -T python-api python buscar.py 1 "¿Qué enfermedad tiene Ana Demo?"
```

Esperado: ambos resultados del paciente 1 y `paciente-1.md`; el primero contiene Enfermedad Alfa en la sección Enfermedad. La salida incluye score, paciente, archivo, sección y texto.

buscar la cirugía que no está en el documento:
```powershell
docker compose exec -T python-api python buscar.py 1 "¿Cuál fue la última cirugía de Ana Demo?"
```

Esperado: dos fragmentos de Ana, de Enfermedad y Tratamiento; ninguno describe cirugía. El score ordena similitud, no garantiza que exista una respuesta.

Código: [búsqueda](../python-api/buscar.py), [embeddings y Qdrant](../python-api/app/knowledge.py), [ingesta](../python-api/ingestar.py) e [historia de Ana](../datos/paciente-1.md). Evidencia: [HDU-013/014 en S03](S03.md).

## 6. Chatbot comparativo

Abre [el chatbot](http://localhost:8000), elige **Ana Demo** y realiza estas dos consultas, una después de la otra:

| Pregunta exacta | Resultado esperado con RAG |
|---|---|
| ¿Qué enfermedad tiene Ana Demo? | Enfermedad Alfa y cita `[paciente-1.md/Enfermedad]` |
| ¿Cuál fue la última cirugía de Ana Demo? | `No hay información suficiente.` |

Pulsa Consultar y espera: el aviso Cargando y los campos bloqueados desaparecen al terminar. Mira las columnas Sin RAG y Con RAG, el paciente/pregunta consultados y las fuentes. La rama directa puede reconocer que no sabe: no necesita inventar una respuesta. Para cirugía, los fragmentos recuperados no acreditan una cirugía.

Ambas ramas usan la misma pregunta exacta, `llama3.2:3b`, temperatura 0, contexto 2048 y máximo 256 tokens. El timeout es 120 segundos por llamada al LLM; se realizan dos llamadas y la recuperación.

Código: [página](../python-api/app/static/index.html), [endpoint](../python-api/app/main.py), [prompt RAG](../python-api/rag.py) y [LLM compartido](../python-api/app/llm.py). Evidencias: [respuestas del ensayo HDU-020](S05/020-resultados.json), [enfermedad](S05/020-caso-1.png), [cirugía](S05/020-caso-2.png) y [cuatro casos HDU-021](S05/021-resultados.json).

Si necesitas guardar automáticamente ambos casos en este equipo, la prueba usa el Node/Playwright local de Codex y Edge. Cada ensayo debe tener un prefijo distinto para conservar las evidencias anteriores.

ubicar Playwright:
```powershell
$env:NODE_PATH = 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
```

guardar en la carpeta de esta etapa:
```powershell
$env:EVIDENCE_DIR = (Join-Path $PWD 'evidencias\S05')
```

usar fecha y hora como prefijo para tu siguiente ensayo:
```powershell
$env:EVIDENCE_PREFIX = Get-Date -Format 'yyyyMMdd-HHmmss'
```

ejecutar enfermedad y cirugía de Ana desde el formulario:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts\verificar_chat_ui.cjs --demo
```

El modo `--demo` y las variables se probaron en HDU-020 y HDU-024. El ensayo HDU-023 usó `--dataset`, que incluye las dos consultas de Ana y además Bruno y Carla. Para tu próxima ejecución se usa fecha/hora como prefijo, sin reemplazar esos resultados. Esperado con `--demo`: código 0, dos respuestas completas en JSON y dos capturas. Código: [verificador UI](../scripts/verificar_chat_ui.cjs). Explicación personal, sesión y valoración de Rui siguen pendientes.
