# HDU-046 · Una réplica lista para la demo · 28/10/2026

**Estado vigente después de HDU-048: dos réplicas Ready.** Esta nota conserva la preparación histórica con una. La [evaluación técnica](evaluacion.md) guarda la escala final 1→2; para otra demo desde una réplica, usa [el restablecimiento por Git](#volver-a-una-réplica-para-otra-demo).

Se cambió `replicaCount: 2` a `replicaCount: 1` en [values.yaml](../../deploy/helm/fastapi/values.yaml) y se publicó el commit **f40aefc436a24f427565e00a9a1e54e2ba7ca3b3** en `main`. Argo CD detectó y aplicó automáticamente la escala; su operación terminó correctamente después del reintento explicado abajo. El 13/01/2027 es la fecha prevista del plan, no la fecha de esta ejecución.

| Resultado final | Evidencia |
|---|---|
| Revisión exacta f40aefc, Synced/Healthy, operación Succeeded | [Comprobación GitOps](046-gitops.json) |
| Un pod Ready, `fastapi-766cfdc5d5-wbd8l`, imagen s09 | [Pods](046-pods.txt) |
| GET de Ana 200 en 8002, mismo cuerpo que Compose en 8000 | [Respuestas guardadas](046-gitops.json) |
| UI con Sync OK, revisión f40aefc y un pod | [Captura inspeccionada](046-argocd.png), [estado de la UI](046-ui.json) |

## Incidencia recurrente y reintento

El primer auto-sync aplicó una réplica, pero volvió a terminar **Error: counter cannot decrease in value**: inicio **19:40:50 UTC**, fin **19:40:45 UTC**, duración negativa. [Estado inicial conservado](046-estado-inicial.json). El pod estaba Ready; el GET 200 se comprobó tras el reintento y la reapertura del túnel. Un pod Ready no bastaba para dar por correcta la operación.

Se solicitó un reintento real de `main` por la API de Argo CD, sobre el mismo commit, sin modificar status ni relojes. Terminó **Succeeded**, inicio y fin **19:42:48 UTC**. [Petición de reintento](046-reintento.json). La recurrencia mantiene abierto el límite externo ya descrito en [HDU-042](../s09/despliegue-inicial.md); no se afirma una corrección definitiva ni que el auto-sync haya pasado a la primera.

El [diagnóstico de reloj](046-reloj.md) capturó un retroceso compartido de unos 3,3 segundos en nodo/controller/servidor mientras Windows avanzaba. No se identificó qué ajusta ese reloj ni una mitigación preventiva soportada en Argo CD 3.5.6. Se conservan las ocho muestras; no se cambiaron relojes ni servicios.

Al ajustar las réplicas, el helper de FastAPI detectó el túnel sin respuesta y abrió otro; esta vez se ejercitó su rama de recuperación del listener propio. El acceso final volvió a dar 200. Para revisar el estado de uso, consulta [la guía](../../GUIA.md#fastapi-desde-git): tras un push solo documental, la revisión comparada puede avanzar sin repetir la última operación de escala. No fuerces una operación solo para igualar esos SHA.

## Cambio preparado para la demo final

Esta secuencia se preparó en HDU-046 y el cambio 1→2 se ejecutó técnicamente en HDU-048. Para repetirla, empieza con una réplica mediante el restablecimiento de abajo; el estado vigente tiene dos. La explicación personal y la revisión de Rui siguen pendientes.

Desde `codigo`, con PowerShell 7, Git en la rama `main` y los servicios disponibles:

ver qué cambios hay antes de empezar:
```powershell
git status --short
```

cambiar únicamente la línea exacta de una réplica a dos:
```powershell
(Get-Content -Raw -LiteralPath 'deploy/helm/fastapi/values.yaml') -replace '(?m)^replicaCount: 1[ \t]*\r?$', 'replicaCount: 2' | Set-Content -LiteralPath 'deploy/helm/fastapi/values.yaml' -Encoding utf8 -NoNewline
```

revisar que el diff muestre solo replicaCount 1→2:
```powershell
git diff -- deploy/helm/fastapi/values.yaml
```

preparar solo ese archivo para el commit:
```powershell
git add -- deploy/helm/fastapi/values.yaml
```

comprobar los archivos preparados (debe aparecer únicamente values.yaml):
```powershell
git diff --cached --name-only
```

Si aparecen otros archivos, revisa ese estado antes de hacer el commit; esta demo solo cambia el número de réplicas.

crear el commit del cambio:
```powershell
git commit -m "Demo final: escalar FastAPI a dos replicas desde Git"
```

guardar el SHA nuevo en esta misma terminal:
```powershell
$revisionDemo = git rev-parse HEAD
```

publicarlo en la rama observada por Argo CD:
```powershell
git push origin main
```

Espera la sincronización automática en [Argo CD](https://localhost:8443/applications/argocd/fastapi), sin pulsar Sync ni escalar con kubectl. Debe aparecer el SHA nuevo, Synced/Healthy y operación Succeeded. Si reaparece el error del contador, conserva el estado y sigue el [reintento documentado](../../GUIA.md#fastapi-desde-git); registra que hubo esa intervención.

comprobar el acceso local de FastAPI:
```powershell
.\scripts\abrir_fastapi_minikube.ps1
```

esperar ese commit exacto, dos pods Ready y GET de Ana 200:
```powershell
python scripts/verificar_gitops.py --commit $revisionDemo --replicas 2 --output evidencias/s10/demo-replicas.json
```

ver los dos pods:
```powershell
.\.local\bin\kubectl.exe --context=genai -n genai get pods -l app=fastapi -o wide
```

consultar a Ana (200):
```powershell
curl.exe -i http://localhost:8002/patients/1
```

Usa el verificador estricto inmediatamente después de este cambio real de réplicas. Guarda el commit, la captura de Argo CD y el JSON junto a la evaluación de la demo. Si repites la prueba, usa otro archivo de salida para conservar la anterior. Un fallo queda registrado con el resultado obtenido y su siguiente acción; no se presenta como una validación recibida.

## Volver a una réplica para otra demo

Hazlo solo si quieres repetir el recorrido desde una réplica. Esta receta queda preparada para una próxima ejecución; **no se aplicó después del cierre HDU-048**, que conserva dos. Desde `codigo`, en `main`, revisa primero `git status --short` y no incluyas cambios ajenos.

cambiar la línea exacta de dos réplicas a una:
```powershell
(Get-Content -Raw -LiteralPath 'deploy/helm/fastapi/values.yaml') -replace '(?m)^replicaCount: 2[ \t]*\r?$', 'replicaCount: 1' | Set-Content -LiteralPath 'deploy/helm/fastapi/values.yaml' -Encoding utf8 -NoNewline
```

revisar que el diff solo muestre replicaCount 2→1:
```powershell
git diff -- deploy/helm/fastapi/values.yaml
```

preparar ese archivo:
```powershell
git add -- deploy/helm/fastapi/values.yaml
```

comprobar que no haya otros archivos preparados:
```powershell
git diff --cached --name-only
```

crear el commit de preparación:
```powershell
git commit -m "Preparar otra demo: una replica FastAPI desde Git"
```

guardar el SHA que acabas de crear:
```powershell
$revisionPreparacion = git rev-parse HEAD
```

publicarlo:
```powershell
git push origin main
```

Espera la sincronización en Argo CD. Si el túnel perdió el pod al reducir las réplicas, ejecuta `abrir_fastapi_minikube.ps1` antes de comprobar el GET.

comprobar el acceso local:
```powershell
.\scripts\abrir_fastapi_minikube.ps1
```

verificar el commit nuevo, una réplica Ready y Ana 200:
```powershell
python scripts/verificar_gitops.py --commit $revisionPreparacion --replicas 1 --output evidencias/s10/nueva-preparacion.json
```

Con esa comprobación correcta puedes volver al [guion](guion.md) y realizar después el cambio 1→2. Si aparece la incidencia del contador, conserva el resultado y el reintento según la guía; no cambies el status para darlo por terminado.
