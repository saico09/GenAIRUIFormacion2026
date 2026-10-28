# HDU-043 · Dos réplicas y reposición de un pod · 28/10/2026

En [values.yaml](../../deploy/helm/fastapi/values.yaml) se cambió `replicaCount` de **1 a 2** y se publicó el commit **4844f919647381ee36e27ef0d2cb7f4170408abe** en `main`. Argo CD detectó ese cambio y terminó la sincronización automáticamente; la operación registra `initiatedBy.automated: true` y la revisión exacta del commit.

| Comprobación | Resultado |
|---|---|
| Sincronización desde Git | Synced, Healthy y operación Succeeded; inicio y fin 19:20:11 UTC |
| Réplicas después del cambio | Dos pods Ready con imagen `genai-fastapi:s09` |
| HTTP tras sincronizar | GET `http://localhost:8002/patients/1` → 200; Ana coincide con Compose |
| Pod eliminado | `fastapi-766cfdc5d5-pf4q5`, UID `ce4c9c95-71fe-431e-917e-263e36832b59` |
| Reemplazo | `fastapi-766cfdc5d5-wbd8l`, UID `9d03d683-2770-4f1f-9f65-8efd8b50926b` |
| Estado recuperado | Dos pods Ready y GET de Ana 200; el otro pod, `fastapi-766cfdc5d5-jw9hn`, se conservó |

Se eliminó exactamente un pod. Kubernetes creó su reemplazo manteniendo las dos réplicas del Deployment: no hubo otro push ni Sync manual para reponerlo, y el commit permaneció igual. [Sincronización](043-gitops.json), [pods iniciales](043-pods.txt), [borrado](043-borrado.txt), [comparación de nombres y UID](043-reemplazo.json) y [comprobación después de la reposición](043-recuperacion.json).

## El túnel local también necesitó recuperarse

Después del borrado, el port-forward de 8002 seguía ligado al pod eliminado. La petición falló con `RemoteDisconnected` aunque Kubernetes ya había repuesto la réplica. Se conservaron el [resultado fallido](043-tunel-fallo.json) y el [log del túnel](043-tunel-error.txt); el GET final pasó al reconstruir ese acceso local.

El helper `scripts/abrir_fastapi_minikube.ps1` ahora comprueba `/health` antes de reutilizar el listener. Se comprobó que abría un túnel nuevo después del fallo del anterior y que una segunda ejecución reutilizaba el túnel sano. El proceso viejo terminó tras la petición fallida: **no se ejercitó específicamente la rama que usa Stop-Process** para cerrar un listener propio que siga vivo sin responder. El código comprueba su propietario antes de cerrarlo y no toca un proceso ajeno que ocupe el puerto.

## Para contarlo con tus palabras

- **Git guarda lo que queremos:** `replicaCount: 2` queda versionado y publicado.
- **Argo CD aplica ese estado:** lee el chart de `main` y actualiza el Deployment en Minikube.
- **Kubernetes mantiene las dos réplicas:** si falta un pod, el controlador lo repone. Esa reposición no necesita un nuevo commit.

La [captura inspeccionada](043-argocd.png) muestra Healthy, Synced, commit `4844f91`, Sync OK y los dos pods. [Estado de la UI](043-ui.json) y [pods después de recuperarse](043-pods-recuperados.txt). La [guía](../../GUIA.md#dos-réplicas-y-reposición) deja la comprobación y el acceso local.

La explicación personal de Marco y la revisión de Rui siguen pendientes; estas frases sirven de apoyo y no acreditan una sesión ni horas realizadas.
