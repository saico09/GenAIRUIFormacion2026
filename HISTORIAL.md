# Historial breve

Qué se fue incorporando y dónde usarlo. Los comandos están en [GUIA.md](GUIA.md).

## 12/11/2026 · Calidad, íconos y limpieza

Se alinearon los íconos y se corrigieron esperas de operaciones de la interfaz. Java valida correo e informes sin los patrones costosos anteriores. El chart de FastAPI declara almacenamiento efímero y no monta un token de Kubernetes que no necesita. Se conservan las cuatro secciones, CRUD, consultas, Markdown, respaldos SQL y RAG.

SonarQube pasó de 49 a 29 avisos: 21 corregidos, uno de un experimento archivado y dos nuevos en pruebas/verificadores. El Quality Gate sigue en ERROR por avisos y cobertura no importada. [Resultados y límites](evidencias/calidad-2026-11-12/LEEME.md).

Se archivaron fuera del proyecto informes de revisión, resultados antiguos y tres experimentos que la app ya no utiliza. Se conservaron las funciones, los datos, las pruebas reutilizables y las guías de uso. El archivo reversible, la copia ZIP previa y Git guardan los históricos; el detalle está en `evidencias/calidad-2026-11-12/limpieza-manifiesto.json`.

Los verificadores de assets, CRUD compartido y conexión de Minikube ahora están en `scripts/`, separados de las salidas de sus pruebas.

## 11/11/2026 · Respuestas breves ante síntomas

El chatbot propone causas y alternativas condicionales sin entrar en un cuestionario. Las posibilidades se mantienen separadas de los antecedentes confirmados. Qwen 3.5 de 4B se ejecuta mediante Ollama, con la misma pregunta, modelo y parámetros en las dos ramas.

Para cambiar las instrucciones: `python-api/rag.py`. El formato se valida en `orientation.py`; las opciones del modelo están en `app/llm.py`. Después, reconstruye Python siguiendo la guía.

## 08/11/2026 · Informes compartidos con Minikube

El CRUD FastAPI desplegado en Minikube usa los mismos pacientes e informes que Compose. `scripts/reanudar_minikube.ps1` recupera el montaje de `datos/historias/`, comprueba SQL y abre los accesos de FastAPI y Argo CD.

## 07/11/2026 · Pacientes, consultas y registros clínicos

Las APIs Python y Java comparten `public.patients`. Crear un paciente genera su Markdown; renombrarlo conserva su historia. Desde **Pacientes**, pulsa un nombre para consultar o editar sus registros y descargar el informe.

| Dato | Dónde queda | Cómo usarlo |
|---|---|---|
| Paciente | `public.patients` | Tabla de Pacientes o CRUD de cualquiera de las APIs |
| Enfermedad, tratamiento y medicamento | `public.patient_diseases` y Markdown | Registros confirmados; UUID común por fila |
| Consulta y respuestas con/sin RAG | `public.medical_consultations` y Markdown | Consultas médicas → Comparar y guardar |
| Versiones completas del informe | `public.medical_consultations` | Respaldo al editar o borrar; SQL en la guía |
| Operación HTTP | `public.transaction_logs` | Un UUID por operación y `patient_id` cuando corresponde |
| Fragmentos para RAG | Qdrant | Sincronización del informe y búsqueda por paciente |

La edición del Markdown pide confirmación y revisión vigente para evitar sobrescribir cambios. Las propuestas de IA se pueden corregir antes de confirmar. El chat guarda sus respuestas como orientación; no las convierte en enfermedades confirmadas. Reintentar la misma consulta conserva su UUID.

Los casos ficticios usan reflujo, diabetes tipo 2 y rinitis alérgica. [CASOS.md](datos/CASOS.md) explica las historias y las preguntas para probarlas.

## 07/11/2026 · Portal de cuatro secciones

HTML, CSS y JavaScript, sin añadir un framework. La barra abre **Consultas médicas**, **Pacientes**, **API Python** y **API Java**. Los exploradores permiten ejecutar las operaciones y distinguen verbos, códigos y errores por color.

## 03/11/2026 · Reanudación y conexión a PostgreSQL

FastAPI reintenta fallos transitorios al arrancar. Minikube se conecta directamente a PostgreSQL por la red Docker, evitando el intermediario del puerto publicado de Windows. El helper de reanudación comprueba la conexión antes de abrir los túneles.

## 27–28/10/2026 · Base incremental de la formación

| Parte | Qué permite | Dónde usarla |
|---|---|---|
| Docker y PostgreSQL | Levantar APIs y conservar datos en volúmenes | `docker compose up -d --build` |
| FastAPI y Spring Boot | CRUD con validación y errores HTTP | Puertos 8000 y 8080 |
| Embeddings y Qdrant | Indexar informes y buscar fragmentos del paciente | `ingestar.py` y `buscar.py` |
| Comparación RAG | Contrastar respuesta directa y respuesta con contexto | Consultas médicas |
| Prometheus y Grafana | Revisar tráfico, errores y latencia | Puertos 9090 y 3000 |
| Loki | Consultar logs HTTP y llamadas del modelo | Grafana → Explore |
| LangGraph y Phoenix | Ver el recorrido RAG y sus tiempos | Puerto 6006 |
| Minikube, Helm y Argo CD | Desplegar el CRUD FastAPI desde Git | `reanudar_minikube.ps1` |

Las copias semanales siguen el avance de cada etapa; sus comandos están en el `LEVANTAR.txt` de cada semana.
