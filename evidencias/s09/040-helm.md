# HDU-040 · Chart y PostgreSQL local · 28/10/2026

El chart [fastapi](../../deploy/helm/fastapi/Chart.yaml) quedó preparado y validado. Su alcance es el CRUD de FastAPI en Kubernetes; el chatbot sigue en [Compose, puerto 8000](http://localhost:8000). En esta HDU no se instaló el Deployment.

| Pieza | Configuración o resultado comprobado |
|---|---|
| Chart | Versión 0.1.0, appVersion s09, Deployment y Service ClusterIP en namespace genai. |
| Imagen y réplica | `genai-fastapi:s09`, IfNotPresent, una réplica y puerto 8000. |
| Readiness | GET `/health` en 8000, initialDelaySeconds 5 y periodSeconds 5. |
| Recursos del pod | Requests 100m CPU/128 MiB; limits 500m CPU/512 MiB. |
| PostgreSQL | Host 192.168.65.254, puerto 5432, base genai; [resolución de host.minikube.internal](040-host.txt). |
| Credenciales | Secret Opaque `genai-postgres`, claves POSTGRES_USER/POSTGRES_PASSWORD; [solo metadatos](040-secret-metadata.txt). |
| Validación Helm | [Lint correcto](040-helm-lint.txt), con recomendación opcional de icono; [manifiestos renderizados](040-helm-template.yaml). |
| Conexión desde pod | [SELECT 1 devolvió 1](040-select1.txt); el pod terminó Succeeded y se eliminó. |

`scripts/crear_secret_postgres.ps1` crea el namespace si falta y aplica el Secret desde el `.env` local mediante stdin y server-side apply. Se ejecutó dos veces: crear y actualizar pasaron. No guarda valores secretos en archivos versionados ni los imprime. El chart referencia el Secret por nombre.

Compose cambió la publicación de PostgreSQL a **5432:5432**, accesible mediante las interfaces del host para que Minikube conecte. Se recreó PostgreSQL conservando `pgdata`: [salida](040-postgres.txt). La comparación anterior/posterior confirmó **cuatro filas Python y tres Java sin cambios**, sin publicar sus datos: [persistencia](040-persistencia.json).

La prueba usa [040-pod-sql.yaml](040-pod-sql.yaml), imagen s09 ya cargada y psycopg; no descarga otra imagen para ejecutar SQL. El manifiesto solo contiene referencias al Secret. [Estado final del pod](040-pod-sql.json) y [salida de creación, SELECT 1 y limpieza](040-select1.txt).

Para repetir, sigue [Chart y conexión a Postgres en la guía](../../GUIA.md#chart-y-conexión-a-postgres): resolver host, crear/actualizar Secret, lint/template, aplicar el pod SQL, esperar Succeeded, leer su 1 y eliminarlo. Usa siempre `--context=genai`. La [nota de conectividad](040-conectividad.md) conserva los comandos exactos y el detalle técnico de la prueba.

Si `host.minikube.internal` devuelve otra IP en otro equipo o perfil, actualiza tanto `postgres.host` de `values.yaml` como `POSTGRES_HOST` del manifiesto SQL. La prueba de esta HDU acredita la conexión y el chart; la instalación y su HTTP se comprueban en el siguiente paso. Explicación personal y revisión de Rui siguen pendientes.
