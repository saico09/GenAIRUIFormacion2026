# HDU-033 · Revisión de logs · 28/10/2026

Se repitieron las consultas guardadas de HDU-031 y HDU-032 contra Loki y en Grafana Explore, conservando sus intervalos. Los registros recuperados son idénticos a la evidencia original. Esta revisión consulta esos logs existentes; no vuelve a generar peticiones ni llamadas al modelo.

| Consulta | Resultado comprobado | Captura |
|---|---|---|
| FastAPI | Dos GET: 200 y 404, con sus request_id | [FastAPI](033-fastapi.png) |
| Spring Boot | Dos GET: 200 y 404, con sus request_id | [Spring Boot](033-springboot.png) |
| Chatbot por request_id | Un POST `/chat` 200 y dos eventos LLM, ramas `direct` y `rag` | [Chatbot](033-chatbot.png) |

Las tres capturas se inspeccionaron. La del chatbot muestra prompt, respuesta y duración de ambas ramas. [Resultado completo](033-revision.json) y [URLs de Explore con los intervalos incorporados](033-explore.json).

FastAPI, intervalo **28/10/2026 17:56:41.286310–17:58:42.393462 UTC**:

```logql
{service="fastapi"} | json | event="http" | request_id=~"hdu031-fastapi-(200|404)-216028e8054e4fa2b2cd3d4b56565f1c"
```

Spring Boot, intervalo **28/10/2026 17:56:41.286310–17:58:42.402260 UTC**:

```logql
{service="springboot"} | json | event="http" | request_id=~"hdu031-springboot-(200|404)-216028e8054e4fa2b2cd3d4b56565f1c"
```

Chatbot, intervalo **28/10/2026 18:05:39.283233–18:07:53.514385 UTC**:

```logql
{service="fastapi"} | json | request_id="hdu032-b1f2ddff60e54e5cb1cb301cf59a9d76"
```

También se repitió la consulta original de HDU-032 con `| event="llm"`: devolvió las dos llamadas esperadas. En la captura de revisión se quitó únicamente ese filtro para mostrar junto a ellas el registro HTTP.

**Frase de apoyo:** el mismo `request_id` une la petición HTTP con sus llamadas directa y RAG, de modo que podemos seguir una consulta concreta sin confundirla con otras.

Corrección de esta revisión: la captura inicial del chatbot cortaba visualmente el último registro. El helper admite ahora `SCREENSHOT_HEIGHT`; su valor predeterminado sigue siendo 1500 y para estas capturas se usó 2200. La repetición mostró los tres registros completos. No fue necesario corregir código de las APIs.

**Revisión de Rui: pendiente.** No se recibieron comentarios ni validación experta; tampoco se acredita que Marco haya explicado todavía el recorrido. No hay información nueva sobre horas desplazadas por TSTT, por lo que no se registran horas reales ni se crean reservas. La incorporación a Git la coordina el cierre de HDU-030–033.

Para abrir y capturar otra vez estas mismas consultas desde `codigo/`:

```powershell
$env:NODE_PATH = 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:EVIDENCE_DIR = 'evidencias/s07'
$env:EVIDENCE_PREFIX = 'revision-local'
$env:SCREENSHOT_HEIGHT = '2200'
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts/capturar_loki.cjs evidencias/s07/033-revision.json
```

El helper usa la contraseña local de `.env` sin imprimirla; las evidencias no incluyen credenciales.
