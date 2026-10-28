# El reloj volvió a afectar la sincronización

En HDU-046, Argo CD aplicó `replicaCount: 1`, pero la operación automática terminó en `Error`: empezó a las 19:40:50 UTC y terminó a las 19:40:45 UTC. Se conserva el [estado inicial](046-estado-inicial.json); no se corrigió a mano su estado.

Esta vez se capturó el salto directamente. Entre dos muestras, Windows avanzó **2,221 s** mientras el controller, el servidor de Argo y el nodo `genai` retrocedieron unos **3,3 s**. Había un solo controller, sin reinicios. Las [ocho mediciones y fuentes](046-reloj-diagnostico.json) muestran la oscilación del reloj Linux compartido. **No se identificó qué componente lo ajusta**: que el entorno use Docker Desktop/WSL2 no permite atribuirle la causa concreta.

El mecanismo coincide con el [issue oficial 30247](https://github.com/argoproj/argo-cd/issues/30247): Argo CD 3.5.6 suma una duración negativa al contador de sincronización; el panic cambia el resultado a Error. La [corrección propuesta 30276](https://github.com/argoproj/argo-cd/pull/30276) seguía abierta al revisar; la última versión estable publicada seguía siendo 3.5.6.

La recuperación pequeña es volver a solicitar una sincronización real de la misma revisión y comprobar `Succeeded`, tiempos coherentes, la réplica Ready y GET 200. Eso ya se repitió correctamente en 046. Es una recuperación operativa, no una solución definitiva al reloj.

No se encontró una opción preventiva soportada de Argo 3.5.6 para este panic. Subir reintentos no tiene respaldo aquí: la operación ya tenía `retry.limit: 5` y el fallo ocurre después del procesamiento normal de reintentos. No se cambiaron relojes, servicios de sincronización, Docker ni Minikube, ni se añadieron esperas artificiales al chart.
