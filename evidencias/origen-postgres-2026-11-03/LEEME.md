# Dónde falla la conexión a PostgreSQL

03/11/2026. El fallo se localizó en el trayecto del **puerto publicado a través de Docker Desktop**. PostgreSQL y Docker Engine seguían respondiendo por rutas directas. La comparación permite evitar ese trayecto; todavía no identifica el defecto interno que bloqueó el backend de Desktop. Las horas siguientes están en UTC.

## Fallo reproducido

Se planearon ocho recreaciones de pods. Las primeras **cuatro** iniciaron correctamente; la **quinta**, `fastapi-5f67b87475-h8jcd` (`10.244.0.16`), no quedó Ready durante la espera de rollout de 180 s y se abortó la serie. La aplicación dispone de una ventana de reintentos de 120 s. Las tres recreaciones restantes no se ejecutaron. [Registro de las cuatro correctas](recreaciones.json) y [log conservado del quinto](fallo-real-h8jcd.txt): trece intentos con ConnectionTimeout, hasta 89,030 s. La lectura posterior del log completo [falló](fallo-real-completo.txt); no se presenta como un registro íntegro de los 120 s.

A las **21:38:32.873602**, el pod emitió un SYN hacia `192.168.65.254:5432`. El nodo lo sacó por `eth0` con SNAT a `192.168.49.2:49832`. En el flujo capturado hay retransmisiones SYN y ningún SYN-ACK; la captura de PostgreSQL no contiene esa llegada. El fallo ocurre antes del intercambio de autenticación o de una consulta SQL. [Captura del nodo](nodo-tcp-frio.txt), [captura de PostgreSQL](pg-tcp-frio.txt) y [sondas durante el fallo](sonda-durante-fallo.jsonl).

Al mismo tiempo, `host/monitor.log` dejó de avanzar a las **21:38:28.678790**. Los clientes Docker del host no completaron su lectura en ocho segundos, mientras WSL sí respondió. El socket proxy devolvió HTTP 500 y el acceso directo a Docker Engine, HTTP 200. [Control de clientes](control-docker-wsl-durante-fallo.json), [proxy ping](engine-unix-ping-durante-fallo.txt), [proxy version](engine-unix-version-durante-fallo.txt), [Engine directo](engine-raw-ping-durante-fallo.txt) y [logs Desktop](desktop-forwarder.txt).

El componente implicado en esa ruta es `com.docker.backend.exe`, cuyos logs identifican `main.gvisor/forwarder` y `main.apiproxy`. Docker documenta que ese backend gestiona el tráfico VM/host, los puertos publicados y las llamadas API en Windows. [Arquitectura oficial de red de Desktop](https://docs.docker.com/desktop/features/networking/). El silencio del log completo no demuestra por sí solo que un paquete no llegara al forwarder. Los errores previos `CloseWrite` coincidían con cierres intencionales de sondas; tampoco prueban la causa del bloqueo.

## Comparación que aisló la ruta

Se conectó **solo el contenedor PostgreSQL existente** a la red Docker `genai`, con IP `192.168.49.10`, conservando su red Compose y prioridad de puerta de enlace. Se utilizó la API directa de Engine porque la de Desktop estaba bloqueada. No se reinició ni sustituyó PostgreSQL: [antes](pg-red-antes.json), [después](pg-red-directa.json) y [misma identidad e inicio](attach-sin-reinicio.json). Docker admite conectar contenedores en ejecución a redes bridge definidas por el usuario. [Documentación oficial](https://docs.docker.com/engine/network/drivers/bridge/).

Desde el mismo pod de control `fastapi-5f67b87475-gn2hx` (`10.244.0.15`), se ejecutaron dos rondas de cuatro sondas por ruta:

| Ruta a la misma base | Resultado |
|---|---|
| Directa: nodo/red `genai` → `192.168.49.10:5432` | **8/8 correctas**, máximo **96,925 ms**: cuatro conexiones libpq completas y cuatro respuestas de protocolo. [Detalle](ab-directa.jsonl) |
| Publicada: nodo → `192.168.65.254:5432` → reenvío Desktop | **8/8 timeouts**, aproximadamente **5 s** cada uno. [Detalle](ab-publicada.jsonl) |

Las sondas usaron libpq con configuración predeterminada y con SSL desactivado, además de mensajes de inicio y SSLRequest sin SQL. No son ocho consultas SQL. Una [comprobación SQL adicional](misma-base-rutas-ab.json) sí obtuvo `SELECT 1` por la ruta directa en **39,043 ms**; la publicada volvió a agotar **5,001 s**. La misma base y el mismo cliente funcionaban al cambiar la ruta, por lo que este fallo no se explica por una consulta lenta, el esquema o una espera de autenticación de PostgreSQL.

## Recuperación de Docker Desktop

El usuario autorizó explícitamente este reinicio, incluida la interrupción de Qdrant y conservando los volúmenes. `docker desktop restart --timeout 120` no consiguió detener el backend bloqueado. `docker desktop stop --force --timeout 45` sí terminó. El primer `docker desktop start --timeout 120` falló al intentar retirar el socket transitorio `Docker/run/dockerInference`: [error de arranque](desktop-error-arranque.txt). Este error apareció durante la recuperación; no se presenta como la causa del bloqueo inicial de red.

La revisión automática rechazó eliminar ese socket. No se repitió la eliminación. Con el backend detenido, se conservó toda la carpeta `AppData/Local/Docker/run` como `run-conservado-20261103-1905` y se creó una carpeta `run` vacía. El siguiente `docker desktop start --timeout 120` funcionó. No se modificaron discos, volúmenes, configuración del daemon ni relojes; tampoco se usó Factory Reset, limpieza de datos o desinstalación.

Se restauraron los nueve servicios Compose principales, los ocho Qdrant semanales que estaban encendidos y el nodo `genai`: [18 nombres coincidentes](contenedores-restaurados.json). Argo CD volvió a consultar GitHub y aplicó `07d0ba3`; el Deployment pasó a `192.168.49.10`, dos réplicas Ready y `Synced/Healthy/Succeeded`. Las consultas RAG conocida y ausente pasaron de nuevo: [resultado](rag-despues-desktop.json).

## Validación del cambio

El [baseline](baseline-comparacion.json), anterior a esta reproducción, confirmó 4/3/4 pacientes con hashes intactos y nueve puntos Qdrant. La [comparación final](comparacion-final.json) vuelve a comprobar esas mismas huellas y cantidades después del cambio de red, la recreación de PostgreSQL y todas las pruebas.

La integración reproducible quedó publicada en `07d0ba315a7c76f4816dd0d35e42a76963213b1c`: el chart usa `192.168.49.10` y `reanudar_minikube.ps1` llama a `conectar_postgres_minikube.ps1` después de esperar PostgreSQL. El helper valida red, dirección libre y prioridad; añade únicamente la conexión de PostgreSQL y reutiliza una conexión correcta. Pasaron la sintaxis PowerShell, Helm lint/render y [ocho casos aislados](prueba_helper_aislada.json) con respuestas Docker simuladas. Esas comprobaciones no sustituyen su ejecución real.

La primera ejecución real del helper reutilizó la conexión conservada y completó el arranque: [registro](reanudar-despues-desktop.txt). Esa primera comprobación SQL aún pudo usar el host anterior mientras Argo CD sincronizaba. Las pruebas siguientes sí usan el Deployment actualizado:

- [Ocho recreaciones de una réplica](recreaciones-ruta-directa.json): **8/8 PASS**. Cada reemplazo tiene UID nuevo, cero reinicios y un único `db_startup` correcto al primer intento, entre 26 y 82 ms. Se conservó la otra réplica Ready; ambas usan `192.168.49.10`.
- [PostgreSQL recreado y perfil reanudado](ciclo-pg-recreado.json): **PASS**. Cambió el contenedor de la base, conservó exactamente el mismo volumen y perdió su conexión adicional, como se esperaba. El helper la repuso con IP `.10` y prioridad `-1`; la red original conserva prioridad `0` y el nodo sigue con una sola red. La reanudación tardó **83,041 s**, comprobó `SELECT 1`, dos réplicas Ready y GET `/patients` 200.
- [Segundo ciclo con la conexión ya existente](ciclo-red-conservada.json): **PASS**, reanudación en **81,317 s**. Se detuvo y arrancó el perfil, el helper reutilizó la red y repitió SQL, dos réplicas Ready y GET `/patients` 200. Los dos reinicios de contenedor observados después en cada pod corresponden a estos dos ciclos deliberados del nodo; la serie anterior de ocho reemplazos terminó sin reinicios.

Los archivos `argocd-ruta-directa.json` y `deployment-ruta-directa.json` se capturaron durante las recreaciones; muestran temporalmente `Progressing` y una réplica disponible. No se usan para acreditar el estado final saludable.

## Estado final comprobado

- CRUD y validaciones correctos en [Python](crud-python.txt), [Java](crud-java.txt) y [Minikube](crud-minikube.txt). Los temporales se eliminaron y los pacientes originales quedaron intactos.
- [Estado final](estado-final.json): dos réplicas Ready, Argo CD `Synced/Healthy/Succeeded` en `07d0ba3`, los mismos hashes de pacientes Python/Java/Minikube y nueve puntos Qdrant. El conteo Qdrant no compara el contenido de sus vectores.
- [Ocho accesos HTTP 200](componentes-recuperados.json). La [primera pasada](componentes-final.json) dio 503 en Loki; después respondió [Ready, sin intervención](loki-recuperado.json). No se guardó el cuerpo del 503, por lo que no se atribuye una causa exacta.
- [18 contenedores encendidos](contenedores-finales.jsonl), correspondientes al inventario original sin los dos capturadores de diagnóstico, ya retirados. El contenedor PostgreSQL tiene nuevo ID por la recreación deliberada y conserva el volumen.

Para uso normal, desde `codigo/` en PowerShell 7, basta `./scripts/reanudar_minikube.ps1`. La [guía](../../GUIA.md#preparar-minikube) incluye la conexión inicial. Los scripts de esta carpeta son ensayos explícitos; `probar_reanudacion.py` detiene el perfil y, con `--recrear-postgres`, recrea la base conservando su volumen.

Los reintentos de arranque anteriores siguen siendo protección útil, pero no recuperaron el trayecto publicado durante el fallo sostenido. La ruta directa elimina esa dependencia para PostgreSQL y pasó las pruebas anteriores. Docker Desktop se recuperó; su defecto interno exacto sigue sin identificarse y no se presenta este cambio como un parche del backend de Docker.
