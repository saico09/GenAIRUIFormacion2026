# HDU-040 · Chart y PostgreSQL desde Minikube

Comprobado el 28/10/2026. El chart quedó en `deploy/helm/fastapi`: Deployment y Service `fastapi`, namespace de la release `genai`, selector `app: fastapi`, una réplica, imagen `genai-fastapi:s09` con `IfNotPresent` y puerto 8000. La readiness consulta `/health` cada cinco segundos después de una espera inicial de cinco segundos. Requests: 100m/128Mi; límites: 500m/512Mi.

La IP obtenida con `minikube --profile=genai ssh -- getent hosts host.minikube.internal` fue **192.168.65.254**. Está en `values.postgres.host`; base `genai`, puerto 5432 y Secret existente `genai-postgres`. [Salida de resolución](040-host.txt).

PostgreSQL ahora publica `5432:5432` en las interfaces del host para aceptar la conexión desde Minikube. Se recreó únicamente `postgres`, conservando su volumen. Las listas completas de pacientes se compararon en memoria antes/después: **4 filas Python y 3 Java, contenido idéntico**, sin guardar el registro personal en las evidencias. [Persistencia](040-persistencia.json), [recreación](040-postgres.txt).

Para crear o actualizar el Secret, desde `codigo/`:

```powershell
.\scripts\crear_secret_postgres.ps1
```

El script lee usuario y clave de `.env`, crea `genai` si falta y envía el Secret por stdin. No deja archivos temporales con credenciales ni las pone en argumentos de procesos. Usa server-side apply para evitar copiarlas a una anotación `last-applied-configuration`. Se ejecutó dos veces correctamente. [Salida](040-secret.txt), [nombre y tipo](040-secret-metadata.txt).

Para repetir la prueba SQL sin escribir credenciales en comandos:

```powershell
.\.local\bin\kubectl.exe --context=genai apply -f evidencias/s09/040-pod-sql.yaml
.\.local\bin\kubectl.exe --context=genai -n genai wait '--for=jsonpath={.status.phase}=Succeeded' pod/postgres-check-hdu040 --timeout=90s
.\.local\bin\kubectl.exe --context=genai -n genai logs pod/postgres-check-hdu040
.\.local\bin\kubectl.exe --context=genai -n genai delete pod postgres-check-hdu040 --wait=true
```

El pod temporal usa la imagen ya cargada y `secretRef: genai-postgres`. Ejecutó **`SELECT 1` → `1`**, terminó `Succeeded` y fue eliminado. [Manifiesto](040-pod-sql.yaml), [resultado y limpieza](040-select1.txt), [estado final del pod](040-pod-sql.json). Si la IP local cambia, hay que actualizar `values.postgres.host` y la IP del manifiesto de prueba antes de repetirlo.

Validación del chart:

```powershell
.\.local\bin\helm.exe lint deploy/helm/fastapi
.\.local\bin\helm.exe template fastapi deploy/helm/fastapi --namespace genai
```

`helm lint` devolvió cero fallos; solo recomienda un icono opcional. [Lint](040-helm-lint.txt), [manifiestos renderizados sin credenciales](040-helm-template.yaml). No se instaló la release Helm durante esta HDU. El despliegue del microservicio corresponde a la HDU-041; RAG y sus servicios siguen funcionando en Compose.

La explicación de Marco y revisión de Rui siguen pendientes; esta comprobación no atribuye horas reales.
