# HDU-031 · Logs en Loki · 28/10/2026

Loki 3.7.9 y Grafana Alloy 1.21.2 están funcionando en Compose. Se comprobaron sus versiones ejecutables, la validez de ambos archivos de configuración y `http://localhost:3100/ready` → 200. Loki necesita unos segundos de inicialización antes de responder como listo; la primera consulta indicó su espera normal de 15 segundos.

Alloy descubre el proyecto `genairuiformacion2026`, filtra los servicios `python-api|java-api` antes de leer logs y los etiqueta como `service="fastapi"` y `service="springboot"`. Conserva las líneas originales. Loki confirmó solo esos dos servicios y únicamente las etiquetas almacenadas `service` y `service_name`: **request_id sigue dentro del JSON**, no es una etiqueta de cada flujo.

El socket Docker está montado con `:ro`; se comprobó `RW=false` en el montaje. No se habilitó un daemon Docker por TCP ni se publicó la interfaz de Alloy. Loki publica solo `127.0.0.1:3100`. Los archivos están en [loki.yml](../../observabilidad/loki.yml) y [alloy.alloy](../../observabilidad/alloy.alloy); los volúmenes `loki_data` y `alloy_data` guardan datos y posiciones de lectura. Copias de esta prueba: [031-loki.yml](031-loki.yml) y [031-alloy.alloy](031-alloy.alloy).

Las imágenes oficiales están fijadas por digest de índice:

- `grafana/loki:3.7.9@sha256:0db216b630ae1f348a1584c67f3cead8b4c1fc839169a39501db664744158e28`
- `grafana/alloy:v1.21.2@sha256:89a5a320168387336b9ac3c850609c3ba7757eadd4ae5f1d819deb35e9854b18`

Grafana conserva Prometheus y tiene además la fuente **Loki**, uid `loki`, URL interna `http://loki:3100`, acceso proxy y edición habilitada para comprobar Save & test.

Se generaron cuatro GET nuevos, con identificadores únicos, sin guardar cuerpos ni modificar pacientes. El verificador encontró exactamente una línea JSON por respuesta:

| API | GET `/patients/1` | GET `/patients/999999` | Coincidencia en Loki |
|---|---:|---:|---|
| FastAPI | 200 | 404 | Dos request_id y status correctos |
| Spring Boot | 200 | 404 | Dos request_id y status correctos |

También se verificaron `event="http"`, método GET, ruta `/patients/{id}` y `duration_ms` numérico. [Respuestas resumidas, cuatro logs, consultas e intervalos](031-loki.json).

Consultas exactas de esta ejecución:

```logql
{service="fastapi"} | json | event="http" | request_id=~"hdu031-fastapi-(200|404)-216028e8054e4fa2b2cd3d4b56565f1c"
```

```logql
{service="springboot"} | json | event="http" | request_id=~"hdu031-springboot-(200|404)-216028e8054e4fa2b2cd3d4b56565f1c"
```

Intervalo consultado: **28/10/2026, 17:56:41.286310–17:58:42.402260 UTC**; equivale a **14:56:41–14:58:42 en Santiago**. El JSON guarda el final de cada consulta. El margen inicial de dos minutos evita perder registros por los segundos de diferencia medidos entre el reloj de Windows y el contenedor.

**Comprobación en Grafana:** Save & test de la fuente Loki pasó; se inspeccionó [su captura](grafana-loki.png). Explore mostró dos líneas por servicio, con status 200/404 y sus request_id visibles: [FastAPI](031-fastapi.png) y [Spring Boot](031-springboot.png). Ambas capturas se inspeccionaron. [031-explore.json](031-explore.json) guarda las consultas, las URLs y el número de líneas. El script [capturar_loki.cjs](../../scripts/capturar_loki.cjs) abrió los intervalos y consultas de `031-loki.json` y comprobó que cada request_id apareciera antes de capturar.

Para repetir la prueba desde `codigo/`:

```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_loki.py --output evidencias/s07/loki-local.json
```

El script genera cuatro identificadores nuevos y guarda las consultas correspondientes. Para validar las configuraciones sin reiniciar los servicios:

```powershell
docker compose exec -T alloy /bin/alloy validate /etc/alloy/config.alloy
docker compose exec -T loki /usr/bin/loki '-verify-config=true' '-config.file=/etc/loki/config.yml'
```

En esta HDU solo se levantaron Loki/Alloy y se recreó Grafana para leer el provisionado. No se reconstruyeron las APIs ni se operó Qdrant. Configuración apoyada en [Docker con Alloy](https://grafana.com/docs/alloy/latest/monitor/monitor-docker-containers/), [filtros de discovery.docker](https://grafana.com/docs/alloy/latest/reference/components/discovery/discovery.docker/) y el [ejemplo local de Loki 3.7.9](https://github.com/grafana/loki/blob/v3.7.9/cmd/loki/loki-local-config.yaml).
