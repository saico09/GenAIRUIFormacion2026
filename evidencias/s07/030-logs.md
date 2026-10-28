# HDU-030 · Logs correlacionados · 28/10/2026

Cada API emite un JSON por petición: `timestamp` UTC, `service`, `event=http`, `request_id`, `method`, `route`, `status` y `duration_ms` numérico. Python usa ContextVar y middleware; Java usa OncePerRequestFilter y el JsonMapper existente. Se conserva un X-Request-ID válido de hasta 128 caracteres (`A–Z`, `a–z`, dígitos, `.`, `_`, `:`, `-`); si falta o es inválido se genera un UUID. La respuesta devuelve el mismo id.

Se ejecutó [verificar_logs.py](../../scripts/verificar_logs.py): GET 200 con id aportado y GET 404 sin id, en ambas APIs. Cada una de las cuatro respuestas coincidió con exactamente un evento JSON de su contenedor; método, ruta normalizada, status, fecha con zona y duración se comprobaron. [Cuatro respuestas y sus cuatro logs](logs-apis.txt). Solo se muestran Ana y errores sintéticos.

Java comprobó además que un id inválido se reemplaza y que una query de prueba no aparece en el log: [evidencia](030-java.json). Python comprobó un 500 en un servidor temporal aislado, cerrado al terminar: conserva el id, registra 500 y devuelve un mensaje genérico sin exponer la excepción; [salida](030-error-python.txt). No se añadió ese endpoint a la aplicación.

No se registran cuerpos de pacientes, emails ni parámetros de consulta en los eventos HTTP. Se desactivó el access log duplicado de Uvicorn; los mensajes de arranque de los runtimes conservan su formato habitual. Las rutas usan `/patients/{id}` y `unmatched` cuando no existe una plantilla.

Para repetir desde `codigo/`:

```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_logs.py
docker compose logs --no-log-prefix --since 2m python-api java-api
```

El verificador filtra por ids únicos dentro de logs recientes: se observó un desfase de unos cinco segundos entre Windows y Docker, por lo que no utiliza una hora absoluta del host como límite.
