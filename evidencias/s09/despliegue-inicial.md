# HDU-042 · Primer despliegue por Argo CD · 28/10/2026

La Application [fastapi.yaml](../../deploy/argocd/fastapi.yaml) sincroniza el repo público, rama **main**, ruta **deploy/helm/fastapi**, hacia el clúster local y namespace **genai**. Tiene sincronización automática, prune y selfHeal. El commit desplegado es **230a161d585a3106969d57d5103256872f001928**.

| Comprobación final | Resultado |
|---|---|
| Argo CD | Synced y Healthy, revisión exacta del commit indicado |
| Operación | Succeeded, `successfully synced (all tasks run)` |
| Tiempos de operación | Inicio 19:13:42 UTC, fin 19:13:43 UTC, 28/10/2026 |
| FastAPI | Una réplica Ready; pod `fastapi-766cfdc5d5-pf4q5`, imagen `genai-fastapi:s09` |
| HTTP Minikube | GET `http://localhost:8002/patients/1` → 200 |
| Persistencia | Ana, id 1, fecha 1990-01-10 y email sintético ana@example.com; el cuerpo coincide exactamente con Compose en 8000 |

Evidencias: [comprobación completa](042-gitops.json), [pods](042-pods.txt), [resultado de la UI](042-ui.json) y [captura final inspeccionada](042-argocd.png). El helper `scripts/abrir_fastapi_minikube.ps1` probó inicio y reutilización del port-forward oculto en 127.0.0.1:8002. La guía deja sus [comandos de uso](../../GUIA.md#fastapi-desde-git); el curl de Ana también se ejecutó y devolvió 200 al comprobar la documentación.

El alcance Kubernetes es el CRUD de FastAPI conectado al mismo PostgreSQL. El chatbot y sus dependencias RAG siguen en Compose, puerto 8000.

## Incidencia y reintento

El primer intento creó los recursos y mostró Synced/Healthy, pero la operación terminó **Error** con `counter cannot decrease in value`. Sus tiempos eran incoherentes: empezó a las 19:09:13 UTC y terminó a las 19:09:07 UTC. Se conservan [estado inicial](042-estado-inicial.json), [comprobación inicial](042-gitops-inicial.json), [UI inicial](042-ui-inicial.json) y [captura inicial](042-argocd-inicial.png); no se presentan como el resultado final correcto.

El mensaje y el tiempo negativo coinciden con el caso descrito en el [issue oficial #30247](https://github.com/argoproj/argo-cd/issues/30247), sobre retrocesos del reloj y el contador de duración de sincronización. Esa coincidencia orienta la explicación; no acredita por sí sola el origen exacto del cambio de reloj local. El [PR #30276](https://github.com/argoproj/argo-cd/pull/30276) seguía **abierto** al consultarlo el 28/10/2026; no se aplicó ese parche ni se afirma una corrección upstream definitiva.

Se pidió una sincronización real mediante la API de Argo CD. La primera petición por SHA fue rechazada porque la Application tiene auto-sync sobre `main`; se repitió solicitando **main**. Esa rama resolvió al mismo commit y la operación pasó a **Succeeded** con los tiempos finales de la tabla. [Detalle del reintento](042-reintento.json). No se parcheó el status de la Application ni se cambiaron relojes.

`scripts/verificar_gitops.py` ahora exige Succeeded y su revisión exacta, además de Synced/Healthy, réplicas Ready y tiempos coherentes. `scripts/capturar_argocd.cjs` exige una operación comprobada y una vista sin Sync error antes de capturar. Así no se confunde un recurso funcionando con una sincronización terminada correctamente.

Si vuelve a aparecer ese mensaje, en la UI usa **fastapi → Sync → main**, espera el resultado y repite el verificador según la guía. En esta ejecución funcionó; no es una garantía de que la incidencia no pueda repetirse.

La explicación de Marco y la revisión de Rui siguen pendientes. No se atribuyen horas ni una sesión realizada.
