# HDU-021 · Repetición y pendientes · 28/10/2026

Se revisaron los resultados de [HDU-020](S05-arranque.md) antes de repetir las pruebas. No quedó un fallo funcional de arranque sobre el entorno existente, CRUD o RAG que exigiera modificar la aplicación. Se conserva este pendiente sin inventar una corrección:

| Caso heredado | Acción y esperado | Obtenido | Estado / siguiente paso |
|---|---|---|---|
| Ciclo completo desde detenido, paso 1 de HDU-020 | Detener Compose sin borrar volúmenes y seguir el README para arrancar todos los servicios | **NO EJECUTADO**. La revisión automática previa rechazó `docker compose stop qdrant` con `blocked by policy`; no se repitió la parada ni se buscó otra forma de detenerlo | Pendiente de poder realizar ese ciclo; no es un fallo del software y no se marca resuelto |

El `up` autorizado en HDU-020 recreó Qdrant automáticamente y se comprobaron nueve puntos conservados. Esa observación queda en S05-arranque y no se usa para afirmar que se ejecutó el ciclo completo. El error auxiliar de conteo PowerShell se corrigió y repitió en HDU-020; no afectó datos ni requirió cambiar el código de la aplicación.

Como no había fallos funcionales por corregir, se repitieron ambos CRUD y las cuatro preguntas, tal como pide el criterio de esta HDU:

| Repetición | Esperado | Obtenido | Estado / evidencia |
|---|---|---|---|
| CRUD Python: crear, listar, consultar, editar, borrar y consultar borrado | 201 / 200 / 200 / 200 / 204 / 404; filas previas intactas | Secuencia completa correcta; temporal ID 12 eliminado y cuatro filas conservadas; 28 entradas inválidas → 422 sin cambios | Aprobado; [salida](S05/021-crud-python.txt) |
| CRUD Java: misma secuencia | 201 / 200 / 200 / 200 / 204 / 404; filas previas intactas | Secuencia completa correcta; temporal ID 10 eliminado y tres filas conservadas; 28 entradas inválidas → 422 sin cambios | Aprobado; [salida](S05/021-crud-java.txt) |
| HTML: ¿Qué enfermedad tiene Ana Demo? · ID 1 | Alfa y fuente de Ana | `Respuesta: Enfermedad Alfa.` / `Fuente: [paciente-1.md/Enfermedad]` | Aprobado; [captura](S05/021-caso-1.png) |
| HTML: ¿Qué tratamiento sigue Bruno Demo? · ID 2 | Beta y fuente de Bruno | `Respuesta: Tratamiento Beta.` / `Fuente: [paciente-2.md/Tratamiento]` | Aprobado; [captura](S05/021-caso-2.png) |
| HTML: ¿Qué medicamento recibe Carla Demo? · ID 3 | Gamma y fuente de Carla | `Respuesta: Medicamento Gamma.` / `Fuente: [paciente-3.md/Medicamento]` | Aprobado; [captura](S05/021-caso-3.png) |
| HTML: ¿Cuál fue la última cirugía de Ana Demo? · ID 1 | Falta de información | `No hay información suficiente.`; fragmentos de Ana sin cirugía | Aprobado; [captura](S05/021-caso-4.png) |

Los tres procesos de verificación terminaron con código 0. Las cuatro capturas se inspeccionaron. [Respuestas completas, preguntas y fuentes](S05/021-resultados.json): se conservan también las respuestas directas, que reconocen falta de información. El verificador cotejó POST exacto, fuentes del paciente correcto y texto visible igual al recibido; se mantuvieron modelo y parámetros de HDU-019.

Comandos ejecutados desde `codigo/`:

```powershell
Get-Content -Raw scripts\verificar_crud.py | docker compose exec -T python-api python - --base-url http://localhost:8000
Get-Content -Raw scripts\verificar_crud.py | docker compose exec -T python-api python - --base-url http://java-api:8080
$env:NODE_PATH = 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:EVIDENCE_DIR = (Join-Path $PWD 'evidencias\S05')
$env:EVIDENCE_PREFIX = '021'
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts\verificar_chat_ui.cjs --dataset
```

No se modificaron rutas, modelos, datos, retrieval ni prompt para producir estos resultados. No se borraron volúmenes y los verificadores limpiaron solo los registros que crearon. Código de la prueba y evidencias quedan listos para el guardado conjunto en Git. Continúan pendientes el ciclo completo desde detenido, la explicación personal y la revisión de Rui; no se registra una valoración ni una sesión recibida.
