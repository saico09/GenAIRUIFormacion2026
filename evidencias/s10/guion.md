# HDU-047 · Guion final · 28/10/2026

Desde `codigo`, en **PowerShell 7**, con el entorno preparado. El ensayo de consultas conservó **una réplica**; no ejecutó el push final 1→2. [Resultado del ensayo](047-ensayo.json). El 14/01/2027 es la fecha prevista del plan, no la fecha de esta ejecución. La explicación personal de Marco y la revisión de Rui siguen pendientes.

## 1. Abrir y comprobar

Sigue [Arrancar en el README](../../README.md#arrancar) y, si hace falta, los [accesos de Argo CD y Minikube](../../GUIA.md#preparar-argo-cd). No incluye detener Qdrant ni repetir el ciclo completo rechazado anteriormente.

comprobar los ocho accesos y guardar otra ejecución:
```powershell
& 'C:\Users\marco\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/verificar_componentes.py --output evidencias/s10/nueva-comprobacion.json
```

Esperado: ocho HTTP 200. [Arranque y correcciones HDU-044](fallos.md). Si falla 8443 o 8002, vuelve a ejecutar su helper según la guía y repite la consulta; conserva el fallo.

## 2. CRUD Python y Java

crear, consultar, editar y borrar solo el temporal del verificador en Python:
```powershell
Get-Content -Raw scripts/verificar_crud.py | docker compose exec -T python-api python - --base-url http://localhost:8000
```

repetirlo en Java:
```powershell
Get-Content -Raw scripts/verificar_crud.py | docker compose exec -T python-api python - --base-url http://java-api:8080
```

Esperado: POST 201, GET/PUT 200, DELETE 204 y GET posterior 404; entradas inválidas 422. Los pacientes previos quedan intactos. [Python comprobado](044-crud-python.txt) y [Java comprobado](044-crud-java.txt). Las tablas están separadas en PostgreSQL: `public.patients` y `java.patients`.

En el ensayo de solo consulta, [Ana en Python](http://localhost:8000/patients/1), [Java](http://localhost:8080/patients/1) y [Minikube](http://localhost:8002/patients/1) devolvieron 200 con los mismos cuatro campos. [Detalle](047-ensayo.json).

## 3. Comparar sin RAG y con RAG

Abre [el chatbot](http://localhost:8000), selecciona **Ana Demo** y envía **¿Qué enfermedad tiene Ana Demo?**. Espera ambas columnas: RAG debe responder Enfermedad Alfa y citar `[paciente-1.md/Enfermedad]`; la rama directa puede pedir contexto. Ambas usan la misma pregunta, `llama3.2:3b` y los mismos parámetros.

[Resultado y captura HDU-044](044-caso-1.png), [respuestas completas](044-resultados.json). Para mostrar el caso que no está en el documento, la pregunta es **¿Cuál fue la última cirugía de Ana Demo?**; se espera «No hay información suficiente» con RAG, como en las [pruebas de etapa 1](../S04.md).

Código para explicar: [endpoint y comparación](../../python-api/app/main.py), [grafo de cuatro nodos](../../python-api/grafo.py), [construcción del prompt](../../python-api/rag.py) y [modelo/parámetros compartidos](../../python-api/app/llm.py).

## 4. Métricas, logs y traza

| Qué abrir | Qué mostrar |
|---|---|
| [Targets de Prometheus](http://localhost:9090/targets) | FastAPI y Spring Boot UP; el ensayo confirmó ambas series `up=1`. |
| [Métricas y capturas de ambas APIs](observabilidad.md#carga-y-dashboard) | 50 GET: 20 válidos y 5 inexistentes por API. El enlace fijo contiene esa carga; muestra req/s, error % y p95. Para otra carga usa [estos comandos](../../GUIA.md#repetir-la-observabilidad). |
| [Explore con la consulta exacta](observabilidad.md#la-misma-pregunta-en-loki-y-phoenix) | Dos eventos LLM con el mismo request_id, ramas direct/rag, prompt completo, respuesta y duration_ms. |
| [Traza RAG en Phoenix](http://localhost:6006/redirects/traces/b19855f8ff27eacdf2c0637d4758d59a) | Raíz rag y cuatro hijos: retrieval → prompt → llamada_llm → respuesta. Abre Info para entradas/salidas y Attributes para request_id. |

El caso guardado usa `hdu045-1d77ef312e904ee58d4f481ac8fc1f55`. El ensayo HDU-047 volvió a encontrar sus **dos eventos LLM y cinco spans**, además de los **nueve puntos Qdrant**. [Consultas y resultados](047-ensayo.json). El p95 del dashboard agrupa peticiones; no mide por separado ese chat. Las duraciones menores de un milisegundo pueden redondearse a 0 en la UI; el JSON conserva sus valores.

## 5. Estado de GitOps y cambio final preparado

Abre [la Application fastapi](https://localhost:8443/applications/argocd/fastapi): debe estar Synced/Healthy. La [última escala comprobada](gitops-preparacion.md) dejó una réplica tras un reintento real por el error recurrente del contador.

ver el pod que queda antes de la demo:
```powershell
.\.local\bin\kubectl.exe --context=genai -n genai get pods -l app=fastapi -o wide
```

Esperado: **un pod 1/1 Running** y [GET de Ana en Minikube](http://localhost:8002/patients/1) con HTTP 200. El ensayo lo conservó así. Un commit documental posterior puede cambiar la revisión comparada sin repetir la última operación; [cómo revisar ambos estados](../../GUIA.md#fastapi-desde-git).

Para el cambio final, sigue la [secuencia exacta 1→2](gitops-preparacion.md#cambio-preparado-para-la-demo-final): editar `replicaCount`, revisar diff, commit, push y comprobar el SHA nuevo, Succeeded, dos pods Ready y GET 200. **Ese push no forma parte del ensayo HDU-047**: se conserva una réplica como punto de partida. Código para explicar: [values](../../deploy/helm/fastapi/values.yaml), [Deployment](../../deploy/helm/fastapi/templates/deployment.yaml) y [Application](../../deploy/argocd/fastapi.yaml).

## Frases de apoyo para explicar

| Componente | Una frase para repasar |
|---|---|
| PostgreSQL | Guarda los pacientes de ambas APIs en tablas separadas y conserva sus datos en el volumen. |
| Qdrant | Guarda los vectores y fragmentos de las historias y recupera contexto filtrado por paciente. |
| Prometheus | Recoge contadores e histogramas de ambas APIs para calcular tráfico, errores y p95. |
| Loki | Permite buscar los eventos HTTP y LLM por servicio y request_id. |
| LangGraph | Ordena retrieval, prompt, llamada al LLM y respuesta, pasando el estado entre los cuatro nodos. |
| Phoenix | Muestra la traza y las entradas, salidas y tiempos de cada nodo RAG. |
| Argo CD | Lee el chart desde Git y aplica el estado declarado al Deployment de Minikube. |

Estas frases son material de apoyo, no una explicación ya realizada por Marco. Queda comprobar que puede explicar el recorrido RAG, qué prueba cada evidencia y la diferencia entre sincronizar réplicas desde Git y reponer un pod.

## Pendientes para la revisión

El ensayo de consulta pasó y mantuvo una réplica; no exigió una corrección adicional del README. Siguen pendientes la explicación personal, la sesión/evaluación de Rui y el cambio final 1→2 durante la demo. El error recurrente de Argo CD se registra con su reintento; no se da por corregido definitivamente. El ciclo completo desde detenido sigue sin ejecutarse por el rechazo automático previo. No se atribuyen horas ni una revisión acordada.
