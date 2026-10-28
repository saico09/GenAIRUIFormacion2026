# HDU-020 · Arranque y comprobación de etapa 1 · 28/10/2026

Se siguió el [README](../README.md) en este equipo ya preparado, sin cambiar modelos, variables ni datos. El ciclo completo de detener todo y volver a arrancar queda **NO EJECUTADO**: una revisión automática previa rechazó detener Qdrant (`blocked by policy`). No se volvió a intentar esa parada ni se ejecutó `down`; no se interpreta esta limitación como un fallo del software.

| Caso / comando o clic | Esperado | Obtenido | Estado / evidencia |
|---|---|---|---|
| Detener Compose sin borrar volúmenes y arrancar todo desde detenido | Ciclo completo reproducido | No se ejecutó la parada por el rechazo anterior | **NO EJECUTADO**, pendiente |
| `docker compose up -d --build` | Servicios disponibles | Código 0; PostgreSQL siguió Running; Compose recreó las APIs y también Qdrant automáticamente | Aprobado para este arranque sobre el entorno existente; [salida](S05/020-compose.txt) |
| `scripts/iniciar_ollama.ps1` | Ollama accesible | `Ollama 0.40.12 ya responde en localhost:11434` | Aprobado; [salida](S05/020-ollama.txt) |
| GET `:8000/health` y `:8080/health` | 200 | 200 en ambas APIs | Aprobado; [estado](S05/020-estado.json) |
| GET `/patients/1` en ambas APIs | 200 y cuatro campos de Ana correctos | 200; ID, nombre, fecha y email iguales al dataset | Aprobado; [estado](S05/020-estado.json) |
| POST Qdrant `/collections/historias/points/count`, `exact=true` | 9 puntos | 9, después de la recreación automática | Aprobado; [estado](S05/020-estado.json) |
| CRUD Python con Test Demo | 201 / 200 / 200 / 200 / 204; GET final 404 | Todos correctos; temporal ID 11 eliminado; cuatro filas previas conservadas | Aprobado; [salida](S05/020-crud-python.txt) |
| CRUD Java con Test Demo | 201 / 200 / 200 / 200 / 204; GET final 404 | Todos correctos; temporal ID 9 eliminado; tres filas previas conservadas | Aprobado; [salida](S05/020-crud-java.txt) |
| HTML: Ana, enfermedad, Consultar | Alfa con fuente | `Respuesta: Enfermedad Alfa.` y `Fuente: [paciente-1.md/Enfermedad]` | Aprobado; [captura](S05/020-caso-1.png) |
| HTML: Ana, última cirugía, Consultar | Falta de información | `No hay información suficiente.` | Aprobado; [captura](S05/020-caso-2.png) |

La recreación de Qdrant la realizó el comando `up` del README; no se pidió por separado y no acredita haber detenido todo Compose. El volumen mantuvo los nueve puntos sin repetir la ingesta. No se borraron volúmenes ni filas previas; las pruebas CRUD compararon silenciosamente su estado inicial y final y limpiaron únicamente su temporal. Los registros guardados contienen códigos, conteos e IDs de prueba, sin el contenido del registro adicional del usuario.

Para repetir las operaciones funcionales, desde `codigo/`:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
.\scripts\iniciar_ollama.ps1
curl.exe -i http://localhost:8000/health
curl.exe -i http://localhost:8080/health
curl.exe -i http://localhost:8000/patients/1
curl.exe -i http://localhost:8080/patients/1
Invoke-RestMethod http://127.0.0.1:6333/collections/historias/points/count -Method Post -ContentType application/json -Body '{"exact":true}'
Get-Content -Raw scripts\verificar_crud.py | docker compose exec -T python-api python - --base-url http://localhost:8000
Get-Content -Raw scripts\verificar_crud.py | docker compose exec -T python-api python - --base-url http://java-api:8080
```

Además de la secuencia CRUD, cada verificador obtuvo 28 respuestas 422 sin alterar filas y comprobó 404 para GET, PUT y DELETE de un ID ausente. No fue necesario añadir comandos de arranque al README para este entorno existente. La reproducibilidad de un arranque completo desde detenido continúa pendiente.

Se añadió al verificador de navegador `--demo` para los dos casos de Ana y variables para guardar cada ensayo sin sobrescribir S04:

```powershell
$env:NODE_PATH = 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:EVIDENCE_DIR = (Join-Path $PWD 'evidencias\S05')
$env:EVIDENCE_PREFIX = '020'
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts\verificar_chat_ui.cjs --demo
```

Ese comando terminó con código 0. [Respuestas completas y fuentes](S05/020-resultados.json); las dos capturas se inspeccionaron. La rama directa reconoció que no tenía información. Las comprobaciones incluyen POST exacto, dos columnas, fuentes, pregunta conservada y bloqueo/restauración de los controles durante la espera.

Una primera comprobación auxiliar de conteo en PowerShell contó el contenedor del array devuelto por `Invoke-RestMethod`, en vez de sus elementos. Se corrigió la lectura del conteo y se repitió: cuatro filas Python y tres Java; los verificadores independientes confirmaron esos mismos números. Fue un error del chequeo auxiliar, sin cambio en la aplicación ni pérdida de datos.

Pendientes: ciclo completo desde detenido, explicación personal y revisión de Rui. No se acredita una sesión, horas realizadas ni valoración humana.
