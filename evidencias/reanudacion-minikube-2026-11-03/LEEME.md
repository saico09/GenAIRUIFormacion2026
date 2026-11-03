# Reanudar Minikube y esperar PostgreSQL

03/11/2026. Cambio `5b406ba` desplegado y probado: dos reanudaciones correctas y datos de pacientes iguales al baseline.

La [lectura previa](baseline-sanitizado.json) dio HTTP 200 en Python, Java y Minikube; 4/3/4 pacientes, hashes Python/Minikube iguales, nueve puntos Qdrant y dos pods Ready. El stop/start **anterior al arreglo** pasó: los mismos pods subieron de 2/6 a 3/7 reinicios, uno por contenedor, compatible con la parada normal. No se reprodujo un fallo nuevo en ese intento. [Arranque](antes-start.txt), [rollout](antes-rollout.txt) y [pods después](antes-pods-tras-start.json).

## Qué se confirmó

El problema de la aplicación era cómo trataba una conexión inicial caída: no fijaba `connect_timeout` y ejecutaba `create_all` una sola vez durante el inicio. Psycopg **3.3.6** usa **130 s** como valor predeterminado cuando ese parámetro falta; está explícito en [conninfo.py oficial](https://github.com/psycopg/psycopg/blob/3.3.6/psycopg/psycopg/conninfo.py#L18-L21). Tras un error de esa conexión, el inicio podía fallar sin reintentarlo dentro del mismo proceso.

`pool_pre_ping=True` comprueba conexiones del pool, pero no convierte una conexión inicial fallida en un ciclo de recuperación del inicio; el error se propaga. [SQLAlchemy 2.1, pooling](https://docs.sqlalchemy.org/en/21/core/pooling.html#disconnect-handling-pessimistic).

Tener el nodo Ready tampoco demuestra que la aplicación pueda consultar PostgreSQL. Minikube distingue sus [esperas de componentes](https://minikube.sigs.k8s.io/docs/commands/start/#options), y el acceso al servicio del host requiere una interfaz accesible y conexión TCP comprobable. [Acceso al host desde Minikube](https://minikube.sigs.k8s.io/docs/handbook/host-access/). **La causa externa de la indisponibilidad transitoria de red no está identificada.** Se corrigió la tolerancia de la aplicación y la secuencia de espera, sin atribuir una reparación de esa red.

## Cambio y pruebas disponibles

- [Inicio de base](../../python-api/app/db.py): conexión limitada a **5 s**, reintentos transitorios cada **2 s**, plazo de inicio de **120 s**. No comienza otro intento vencido el plazo; una conexión ya iniciada puede añadir hasta **5 s** para un host. Este límite no acota el tiempo de consultas DDL. No se reintentan escrituras CRUD automáticamente.
- Los eventos `db_startup` guardan estado, intentos, tiempo y tipo/código del error; omiten texto de la excepción, URL y credenciales. Los errores con SQLSTATE permanente identificable fallan sin repetir; algunos fallos de autenticación llegan sin SQLSTATE y quedan acotados por el plazo.
- [Helper de reanudación](../../scripts/reanudar_minikube.ps1): espera PostgreSQL, reanuda solo `genai`, comprueba `SELECT 1` desde un pod temporal con la configuración desplegada, limpia ese pod y espera las réplicas/Argo antes de abrir los túneles. La comprobación SQL admite 120 s de reintentos, con límite del pod de 150 s y espera de Kubernetes de 160 s. El helper directo de FastAPI también espera el rollout.
- [Ocho pruebas unitarias](unit-db.txt): correctas, incluidos límite, recuperación, errores permanentes y paso real de `connect_timeout=5` a Psycopg.
- [Integración con proxy TCP efímero](integracion-db.txt): recuperación en **14,138 s**, con **tres intentos**; ruta sin respuesta, fallo controlado en **12,005 s** con plazo de prueba de 12 s y dos intentos. PostgreSQL y Qdrant siguieron funcionando. Esto prueba recuperación en el mismo proceso, no reproduce por sí solo la causa externa original.

## Recuperación real de la imagen nueva

Argo [desplegó automáticamente `5b406ba`](gitops-nueva-imagen.json) y quedó Synced/Healthy con operación Succeeded. Durante ese despliegue, el pod `fastapi-5f67b87475-9sftt` registró un **ConnectionTimeout a los 5,002 s** en el primer intento y quedó listo en el segundo, a los **7,081 s**, con **cero reinicios**: el proceso recuperó la conexión sin caerse. La segunda réplica inició en **0,058 s**, también sin reinicios. [Registro de recuperación](rollout-recuperacion-real.txt), [segunda réplica](rollout-segunda-replica.txt) y [estado de pods](nueva-imagen-pods.json). Este último conserva además un pod antiguo que ya estaba terminando; no es una tercera réplica del despliegue nuevo.

El [helper con el perfil encendido](helper-encendido.txt) comprobó `SELECT 1 = 1`, limpió su pod temporal y terminó con **dos réplicas Ready y GET /patients 200**. La recuperación real demuestra la tolerancia al fallo inicial; no identifica ni acredita haber eliminado su causa externa de red.

## Reanudaciones y datos finales

| Escenario | Resultado del helper | Evidencia |
|---|---|---|
| Perfil `genai` detenido, PostgreSQL saludable | PASS en **82,809 s** | [Tiempo](despues-reanudar-1.json), [salida](despues-reanudar-1.txt) |
| Perfil `genai` y PostgreSQL detenidos, levantados en orden | PASS en **97,606 s** | [Tiempo](despues-reanudar-2.json), [salida](despues-reanudar-2.txt) |

Ambos terminaron con SQL correcto, dos réplicas Ready y GET /patients 200. Los dos pods nuevos acumularon dos reinicios cada uno, correspondientes a las dos paradas, sin reinicios adicionales por fallo de inicio. El [CRUD de Minikube](crud-minikube.txt) también pasó: creación, lectura, edición, borrado, 404 y validaciones 422, conservando las cuatro filas previas.

La [lectura final sanitizada](estado-final-sanitizado.json) y la [comparación](comparacion-datos.json) confirman **4/3/4 pacientes en Python/Java/Minikube y los mismos SHA-256 completos del baseline**; Python y Minikube coinciden. Las tres APIs responden 200, Qdrant conserva nueve puntos y Argo está Synced/Healthy/Succeeded en `5b406ba2088698865d3c0f7a1f4f9392af7ecd85`, con la imagen nueva y dos Ready. Qdrant no se detuvo; aquí se compara su conteo, no el contenido de los vectores.

También pasaron los CRUD completos de [Python](crud-python.txt) y [Java](crud-java.txt), la [comparación real con/sin RAG](chat-rag.json) para dato conocido y dato ausente, y los [ocho accesos HTTP](componentes-final.json). Los helpers [reutilizaron los túneles sanos](tuneles-reutilizados.json) conservando sus procesos, sin duplicarlos. Las copias semanales conservan su versión histórica; este arreglo corresponde al proyecto principal.

Para repetir solo las lecturas desde `codigo/`, usando nombres nuevos para conservar esta evidencia:

```powershell
python .\evidencias\reanudacion-minikube-2026-11-03\capturar_estado.py --salida .\evidencias\reanudacion-minikube-2026-11-03\otra-lectura.json --comparacion .\evidencias\reanudacion-minikube-2026-11-03\otra-comparacion.json
```

El [script](capturar_estado.py) ordena la lista completa por `id`, serializa JSON UTF-8 con claves ordenadas y sin espacios, y calcula SHA-256 sin guardar cuerpos de pacientes. La causa externa de red sigue sin identificar; estos ensayos acreditan recuperación y conservación de datos en los escenarios comprobados.
