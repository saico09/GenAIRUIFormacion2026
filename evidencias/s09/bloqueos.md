# Bloqueos de lectura Git · HDU-041

Estado al **28/10/2026: cero bloqueos activos de conexión o lectura Git en Argo CD**. La conexión devuelve Successful y descubre `deploy/helm/fastapi` de tipo Helm en el commit publicado `1bc6af1235a6d96952334e41685c3acd829b3fed`.

| Problema observado | Causa comprobada | Corrección y resultado |
|---|---|---|
| HTTP 404 al consultar el descubrimiento de aplicaciones del repo | El verificador omitía `appProject`, por lo que no consultaba con el proyecto default | Se añadieron `appProject=default` y `appName=fastapi`. La repetición encontró el chart; [resultado](041-repositorio.json) y [UI Successful](041-ui.json). |

Fue una corrección del verificador; no hizo falta cambiar el acceso público del repositorio ni añadir credenciales Git. La [captura](041-argocd.png) se inspeccionó.

Este registro se limita a la lectura Git de HDU-041. Los pendientes de explicación/revisión humana y la prueba completa desde detenido de HDU-020 conservan su estado en [el control general](../s08/control.md).
