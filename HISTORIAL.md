# Historial de la app

## Síntomas breves y portal recuperado · 11/11/2026

La pestaña abierta conservaba el HTML antiguo; al recargar reaparecieron las cuatro secciones. Los pacientes, CRUD clínicos, Markdown, respaldos y logs seguían en el servidor. Si actualizas el proyecto con la página abierta, recarga esa pestaña.

El chat pasa a Qwen 3.5 de 4B mediante Ollama, con temperatura 0.2 y el mismo modelo y pregunta en ambas ramas. Las causas posibles, sus condiciones y los detalles opcionales salen en una estructura validada que la página muestra como texto. Las instrucciones siguen en `python-api/rag.py`; el formato compartido está en `python-api/orientation.py`. Las hipótesis no sustituyen los registros confirmados.

RAG se ejecuta antes de la respuesta directa para agrupar las dos generaciones. Los logs separan carga del modelo, procesamiento y generación. [Pruebas, comparación y límites](evidencias/revision-funcional-2026-11-11/LEEME.md). La entrada siguiente conserva el corte anterior con Gemma.

## Hipótesis ante síntomas · 11/11/2026

Al describir síntomas, el chat ofrece una hipótesis principal y alternativas condicionales con la información escrita, sin pedir más datos ni repetir preguntas. Las posibilidades quedan como orientación en las respuestas guardadas; no crean registros confirmados de enfermedad, tratamiento o medicamento. Las consultas sobre antecedentes siguen limitadas a lo documentado.

Esta revisión configura Gemma 4 (`gemma4:12b`) mediante Ollama, con los mismos parámetros y la misma pregunta en ambas ramas. Se corrigió la confusión entre un relato actual y una consulta anterior parecida, incluida la palabra «constante», que se confundía con «consta en el historial».

Pasaron los dos relatos originales con guardado y reintento, las consultas al historial, propuestas, trazas y el recorrido de la página. La comparación puede tardar unos minutos y el modelo aún puede usar términos imprecisos en sus alternativas: [pruebas y límites](evidencias/hipotesis-2026-11-11/LEEME.md). Este ajuste personal no añade HDU, horas ni cambia las fechas.

## Informes compartidos con Minikube · 08/11/2026

El CRUD de Minikube usa los mismos pacientes e informes que Compose. `scripts/reanudar_minikube.ps1` recupera la carpeta compartida, comprueba escritura y SQL, y abre los accesos cuando las réplicas están disponibles. Si falta el marcador del montaje, la API impide escribir en una carpeta alternativa.

El [ensayo integral](evidencias/pacientes-unificados-2026-11-07/gitops/montaje-real.json) pasó seis bloques: CRUD cruzado, coincidencia MD/SQL, bloqueo sin marcador, pérdida del proceso de montaje, reanudación y conservación de datos. [Argo](evidencias/pacientes-unificados-2026-11-07/gitops/despliegue.json) quedó Synced/Healthy con dos réplicas durante el ensayo. Al cerrar, Minikube volvió a detenido; Compose sigue siendo el acceso habitual.

S9/S10 incorporan el chart y el montaje con sus perfiles propios y una guía `GITOPS.md`. Su GitOps se validó estáticamente; los diez entornos semanales sí se probaron con Compose. No se añadieron HDU ni horas al plan.

## Pacientes compartidos y registros editables · 07/11/2026

Python y Java comparten `public.patients`: los pacientes creados desde cualquiera de las APIs aparecen también en la página. Cada alta genera su Markdown. `public.patient_diseases` guarda enfermedad, tratamiento y medicamento con el mismo UUID que aparece en el informe y con `patient_id` como relación.

En **Pacientes → nombre → Registros confirmados** se puede agregar, editar y eliminar cada fila, con los cambios reflejados en el Markdown. Ambas APIs ofrecen el CRUD `/patients/{id}/diseases`. Los informes y sus consultas siguen respaldados en `public.medical_consultations`.

`public.transaction_logs` conserva un solo UUID `id` por operación y añade `patient_id`. Las semanas usan los mismos puertos de la versión principal; se ejecuta una por vez, con sus volúmenes propios. Postman pasa a peticiones manuales con URLs explícitas y sin scripts.

El [recorrido de navegador real](evidencias/pacientes-unificados-2026-11-07/ui-real/resultados.json) pasó alta desde Python, tabla y CRUD desde la página, edición/descarga Markdown, rechazo de una revisión antigua y conservación del diario. El paciente temporal se retiró y las historias anteriores conservaron su hash. Los nueve guiones Word se revisaron visualmente y se reemplazaron en Drive con texto remoto comprobado; S6 sigue unida a S7.

Esta es una ampliación solicitada por Marco. Las HDU, las 80 horas previstas y las fechas de Rui no cambian. Los apartados siguientes conservan la arquitectura y los resultados de cada corte histórico.

Qué se agregó y cómo usarlo. Comandos en [GUIA.md](GUIA.md). Cada HDU describe su momento; los ensayos no acreditan explicación personal ni revisión de Rui.

## Casos realistas · 07/11/2026

Ana ahora tiene un caso de reflujo con omeprazol; Bruno, diabetes tipo 2 con metformina; Carla, rinitis por polen con cetirizina. Las personas y su evolución siguen siendo inventadas. [Casos, preguntas y fuentes](datos/CASOS.md).

La actualización conserva los UUID y las consultas anteriores, respalda el Markdown en SQL y sincroniza Qdrant. El prompt admite enfermedades reales sin completar antecedentes faltantes: una dosis habitual no demuestra la dosis del paciente, y alergia al polen no significa alergia a medicamentos. [Pruebas de esta revisión](evidencias/corpus-realista-2026-11-07/LEEME.md).

Pasaron 14 preguntas RAG y 35 contratos en el principal, más siete consultas y sus reintentos en las copias. Trello, Postman y las entregas locales quedaron alineados; el Word S3 se actualizó en Drive. [Cierre y límites](evidencias/corpus-realista-2026-11-07/entrega-semanal.json).

## Consultas persistentes · 07/11/2026 · Informe y respaldo SQL

**Comparar y guardar** conserva la consulta y las dos respuestas en el informe del paciente y en `java.medical_consultations`. La página Pacientes muestra esas consultas por fecha, separadas de la tabla de enfermedad, tratamiento y medicamento confirmados. El reintento de la misma consulta conserva su UUID para no duplicarla; actualizar el índice RAG tiene su propio reintento.

`public.transaction_logs` registra las ejecuciones de Python y Java, con cuerpos, verbo, operación y código HTTP. Los nombres están en inglés y `snake_case`. Las ediciones de los registros siguen pidiendo confirmación; el historial original de consultas se conserva. Esta ampliación fue solicitada por Marco y no se presenta como requisito original de Rui.

Se eligió **Qwen3 4B Instruct 2507** para ambas ramas tras comparar los mismos ocho casos con el mismo prompt y parámetros: Qwen pasó 8/8 y Llama 6/8. La respuesta con contexto ahora diferencia antecedentes documentados y orientación sobre síntomas nuevos, sin confirmar diagnósticos automáticamente. [Comparación local](evidencias/consultas-automaticas-2026-11-07/modelos-ab-final.json); no acredita precisión clínica general.

Las copias S4–S10 pasaron siete consultas reales y sus reintentos, con datos conservados y sin duplicados. S3 sólo adapta el parser; S1/S2 no cambian. Se actualizaron guías locales y Trello; los guiones y Word anteriores se conservan. [Cierre y alcance](evidencias/consultas-automaticas-2026-11-07/entrega-semanal.json).

Se mantienen las 80 horas previstas, las dos etapas de 40 horas y las fechas del plan. Los apartados siguientes describen cortes anteriores.

## Historia clínica · 07/11/2026 · Registros confirmados y pacientes Java

Entrega semanal cerrada: ocho copias actualizadas y comprobadas, 14 consultas RAG y cuatro casos de propuesta reales; siete Word reemplazados en Drive y texto remoto verificado. S1/S2 y aviso S6 se conservan, con S6 unida a S7. Postman mantiene diez carpetas, 98 peticiones, 59 variables y las cinco peticiones originales; se corrigieron sus comprobaciones de fuentes y trazas en la colección existente. Trello quedó en 48 Testing y 233/241 pasos, con los mismos ocho pendientes humanos/documentales. [Resumen de la entrega y alcance de las pruebas](evidencias/clinica-2026-11-07/entrega-semanal.json).

Para la primera carga Java se añadió `inicializar_java.py`: asocia los tres informes a los IDs del dataset sólo con tabla vacía y conserva los datos existentes. Diez comprobaciones reales pasaron sobre PostgreSQL y Java nuevos y aislados. [Arranque limpio comprobado](evidencias/clinica-2026-11-07/bootstrap-java.md).

Pasaron 19 consultas RAG, el recorrido completo del navegador con IA real, extracción de propuestas sin guardar, ambos CRUD, métricas/logs/trazas y reanudación del despliegue CRUD en Minikube. Se conservaron los cuatro pacientes Python, tres Java y sus informes; las pruebas usan temporales propios. [Resultados y límites](evidencias/clinica-2026-11-07/LEEME.md).

- Pulsa un nombre en **Pacientes** para ver su tabla clínica y el Markdown, descargarlo o editarlo con confirmación. Cada registro tiene UUID y tres campos; los vacíos siguen vacíos.
- **Nueva consulta** extrae propuestas de una nota ficticia, muestra su evidencia y permite corregirlas o usar un formulario manual. Sólo se guarda tras confirmar; una respuesta del chat no se archiva automáticamente.
- Java conserva el informe en `datos/historias/`; Python sincroniza Qdrant y usa esa misma identidad en el chat. Guardar, renombrar o eliminar actualiza el índice, con reintento separado si falla. El CRUD Python sigue independiente.
- Revisión del Markdown para evitar sobrescrituras, TOP3 y selección RAG de citas literales comprobadas contra sus fuentes. Un filtro conservador limita las preguntas a los hechos registrados; no garantiza la interpretación del modelo. [Quince casos RAG comprobados](evidencias/clinica-2026-11-07/rag-clinico-final.json).
- [Recorrido de pantalla con LLM real](evidencias/clinica-2026-11-07/interfaz.md) correcto: propuesta, confirmación, edición, consulta del cambio y limpieza. Se corrigió una propuesta descartada porque el modelo había reformulado su evidencia; ahora el servidor la copia de la nota. Los datos previos quedaron conservados.
- Ampliación solicitada por Marco, sin nuevas HDU, horas ni revisión de Rui atribuida. [Uso](GUIA.md#historia-clínica).

## Revisión RAG · 07/11/2026 · Calidad de respuestas y almacenamiento

Se reprodujeron respuestas y citas sin respaldo en preguntas abiertas. Doce consultas nuevas y un A/B de 24 respuestas separan los límites del corpus, el TOP2 y el prompt. La variante más estricta con tres fragmentos mejoró los seis casos ensayados, pero no se aplicó a la app. PostgreSQL sigue guardando pacientes; los Markdown alimentan Qdrant y no almacenan las preguntas nuevas. [Resultados y propuesta](evidencias/revision-rag-2026-11-07/LEEME.md). La validación anterior cubría casos preparados; no acreditaba calidad general.

## Interfaz · 07/11/2026 · Consultas, pacientes y APIs

Cuatro secciones en [la página](http://localhost:8000): comparación con/sin RAG, tabla de pacientes conectada a Spring Boot y exploradores de Python y Java con verbos, respuestas y errores por color. La tabla permite agregar, editar, buscar y borrar con confirmación; Java y Python mantienen sus registros separados. Sigue siendo HTML, CSS y JavaScript, sin un framework nuevo. Mejora solicitada por Marco sobre las APIs existentes; no agrega HDU ni cambia el calendario de Rui. Uso en [GUIA](GUIA.md#usar-la-página) y [pruebas](evidencias/ui-2026-11-07/LEEME.md).

La interfaz se adaptó y probó en S4–S10, con datos conservados y S1–S3 intactas. Guiones, Word de Drive y comandos semanales actualizados; S6 continúa unida a S7. Las cuatro preguntas RAG reales pasaron en el entorno principal.

## Conexión directa · 03/11/2026 · PostgreSQL en la red de Minikube

Se reprodujo el corte en el intermediario de Docker Desktop: la misma base respondió por la red Docker y falló por el puerto publicado del host. Minikube ahora usa `192.168.49.10`; `.\scripts\reanudar_minikube.ps1` asegura esa conexión, incluso si se recrea el contenedor PostgreSQL. Pasaron ocho reemplazos de pods y dos reanudaciones, una con PostgreSQL recreado y su volumen conservado. Docker Desktop se recuperó con el reinicio autorizado; su defecto interno no está identificado. [Pruebas y diagnóstico](evidencias/origen-postgres-2026-11-03/LEEME.md).

## Reanudación · 03/11/2026 · Minikube y PostgreSQL

FastAPI reintenta las conexiones iniciales transitorias a PostgreSQL. Para retomar, usa `.\scripts\reanudar_minikube.ps1`: espera la base, comprueba SQL desde el perfil y abre los túneles con las réplicas listas. Pasaron dos reanudaciones, una también con PostgreSQL detenido, conservando los datos; [pruebas y detalle del arreglo](evidencias/reanudacion-minikube-2026-11-03/LEEME.md).

## Guías · 03/11/2026 · Revisión de Claude

- README, GUIA y LEVANTAR recortados a comandos y notas necesarias; se conserva la procedencia aparte.
- [GUIA original](evidencias/revision-claude/documentacion-original/GUIA.md) e [HISTORIAL original](evidencias/revision-claude/documentacion-original/HISTORIAL.md) archivados completos antes del recorte.

## Revalidación · 03/11/2026 · Proyecto completo

- Arranque desde detenido, ambas APIs, datos conservados, RAG y observabilidad comprobados de nuevo; [resultados](evidencias/revision-claude/LEEME.md).
- GitOps repitió una → dos réplicas por commit/push y auto-sync. Los logs ahora generan una salida nueva por ensayo; `.idea` queda local y fuera de Git.
- Para reanudar Minikube, la guía espera que FastAPI arranque antes de abrir su túnel.

## Herramientas · 29/10/2026 · PowerShell y Python

- PowerShell 7.6.9 y Python 3.15.2 instalados; los comandos locales usan `python`.
- Usar PowerShell 7; los helpers no están preparados para Windows PowerShell 5.1.

## HDU-048 · 28/10/2026 · Escala final comprobada, evaluación pendiente

- Escala 1→2 por Git comprobada, con auto-sync y datos conservados.
- Demo y evaluación humana pendientes; recorrido en [evaluacion.md](evidencias/s10/evaluacion.md).

## HDU-047 · 28/10/2026 · Guion final y ensayo de consultas

- Guion final ensayado con una réplica, antes de la escala final.
- Usar [guion.md](evidencias/s10/guion.md); sus frases son apoyo, no explicación personal recibida.

## HDU-046 · 28/10/2026 · Una réplica para iniciar la demo

- Preparación a una réplica; Argo terminó bien tras un reintento real.
- Preparar otra demo con [gitops-preparacion.md](evidencias/s10/gitops-preparacion.md); el problema de reloj sigue abierto.

## HDU-045 · 28/10/2026 · Reproducir métricas, logs y trazas

- Carga de tráfico, paneles y una pregunta correlacionada en Loki/Phoenix.
- Repetir desde la guía; [observabilidad.md](evidencias/s10/observabilidad.md) guarda el ensayo original.

## HDU-044 · 28/10/2026 · Repetir arranque y corregir accesos

- CRUD/RAG revalidados; se corrigieron porcentaje de errores sin serie y túnel HTTPS de Argo.
- Consultar [fallos.md](evidencias/s10/fallos.md) y usar `verificar_componentes.py`.

## HDU-043 · 28/10/2026 · Dos réplicas y reposición de un pod

- Dos réplicas por Git y reposición de un pod comprobadas.
- Tras reemplazar un pod, recuperar el túnel con `abrir_fastapi_minikube.ps1`; evidencia en [gitops.md](evidencias/s09/gitops.md).

## HDU-042 · 28/10/2026 · Primer despliegue desde Git

- Argo desplegó FastAPI; GET devolvió los mismos datos que Compose.
- Acceso por `abrir_fastapi_minikube.ps1`. El reintento superó el fallo de reloj, sin corregir su causa.

## HDU-041 · 28/10/2026 · Argo CD conectado al repositorio

- Argo CD instalado y conectado al repositorio; chart descubierto.
- Abrir con `abrir_argocd.ps1`; la Application se añadió en HDU-042.

## HDU-040 · 28/10/2026 · Chart y conexión local a PostgreSQL

- Chart, Secret y conexión desde Minikube a PostgreSQL preparados.
- [Pasos SQL y Helm](evidencias/s09/040-helm.md). Solo se prepara el CRUD FastAPI; el chatbot queda en Compose.

## HDU-039 · 28/10/2026 · Minikube e imagen FastAPI preparados

- Minikube y herramientas locales preparados; imagen FastAPI construida y cargada.
- Comandos originales en [039-resumen.md](evidencias/s09/039-resumen.md); usar siempre el contexto explícito.

## HDU-038 · 28/10/2026 · Control y pasos de regreso

- Control de una pregunta completa: respuestas, métricas, logs y trazas.
- [control.md](evidencias/s08/control.md) conserva el ensayo y el receso previsto, sin atribuir sesiones realizadas.

## HDU-037 · 28/10/2026 · Entradas y salidas de cada nodo

- Cuatro spans hijos muestran entradas, salidas y duración de cada nodo.
- `verificar_traza.py` comprueba raíz, hijos y correlación en Loki; abrir la URL del JSON.

## HDU-036 · 28/10/2026 · Primera traza RAG en Phoenix

- Phoenix y OpenTelemetry añadidos; primera raíz `rag` comprobada.
- Abrir Phoenix en 6006; los hijos de los nodos se incorporan en HDU-037.

## HDU-035 · 28/10/2026 · Chatbot conectado al StateGraph

- La rama RAG de `/chat` pasó a ejecutar el StateGraph.
- Probar enfermedad y cirugía de Ana en el chatbot; [casos-chatbot.md](evidencias/s08/casos-chatbot.md) conserva ambos resultados.

## HDU-034 · 28/10/2026 · RAG como grafo de cuatro nodos

- Grafo independiente: retrieval → prompt → llamada_llm → respuesta.
- `grafo.py` guarda su estado JSON; todavía no estaba integrado al endpoint en esta HDU.

## HDU-033 · 28/10/2026 · Correlación de logs revisada

- Consultas de logs HTTP y LLM repetidas con el mismo request_id.
- En Grafana Explore filtrar por servicio e id; [revisión](evidencias/s07/revision.md) conserva el resultado.

## HDU-032 · 28/10/2026 · Prompt y respuesta del LLM en Loki

- Las llamadas direct/rag registran modelo, prompt, respuesta y duración.
- `verificar_llm_logs.py` coteja ambas ramas; usar datos ficticios porque el log incluye el contexto.

## HDU-031 · 28/10/2026 · Logs de ambas APIs en Loki

- Loki/Alloy recogen los logs de ambas APIs y Grafana los consulta.
- `verificar_loki.py` genera peticiones y busca sus eventos; no reutilizar ids de evidencias antiguas.

## HDU-030 · 28/10/2026 · Logs JSON y request_id

- Logs JSON HTTP y cabecera X-Request-ID en ambas APIs.
- `verificar_logs.py` coteja respuestas y eventos; desde la revisión del 03/11 crea archivos nuevos.

## HDU-029 · 28/10/2026 · Métricas revisadas

- Contadores y seis paneles revalidados tras tráfico correcto y erróneo.
- Resultados en [revisión de métricas](evidencias/s06/revision.md); explicación propia y revisión de Rui pendientes.

## HDU-028 · 28/10/2026 · Latencia p95 y carga comprobada

- Dashboard ampliado con p95; carga de 50 GET distribuida en unos dos minutos.
- `generar_trafico.py` llena los paneles sin modificar pacientes. El p95 es agregado, no tiempo de red.

## HDU-027 · 28/10/2026 · Dashboard de tráfico y errores

- Dashboard con tráfico y errores, separado por API.
- Abrir Grafana → APIs GenAI; definición en `observabilidad/dashboard.json`.

## HDU-026 · 28/10/2026 · Java, Prometheus y Grafana conectados

- Métricas Java, Prometheus y Grafana conectados.
- Ver targets en 9090 y dashboard en 3000; credenciales de Grafana solo en `.env`.

## HDU-025 · 28/10/2026 · Métricas HTTP en FastAPI

- FastAPI expone contador e histograma HTTP con rutas normalizadas.
- Consultar `/metrics` o ejecutar `verificar_metricas.py`.

## HDU-024 · 28/10/2026 · Preparación de demo comprobada

- Preparación de la demo comprobada con ambas APIs y dos preguntas.
- [Validación](evidencias/S05-validacion.md): la demo y la valoración de Rui quedaron pendientes.

## HDU-023 · 28/10/2026 · Ensayo y espera de disponibilidad

- Se corrigió la consulta demasiado temprana tras Compose con una espera acotada.
- Ejecutar `esperar_apis.ps1` después del arranque; [ensayo](evidencias/S05-ensayo.md).

## HDU-022 · 28/10/2026 · Guion de demo de etapa 1

- Guion de la primera demo: arranque, CRUD, persistencia, búsqueda y chat.
- Seguir [S05-guion.md](evidencias/S05-guion.md), usando temporales propios para CRUD.

## HDU-021 · 28/10/2026 · Repetición y pendientes concretos

- Repetidos ambos CRUD y las cuatro preguntas sin cambiar los datos originales.
- [S05-pendientes.md](evidencias/S05-pendientes.md) registra lo técnico y lo no acreditado en ese corte.

## HDU-020 · 28/10/2026 · Arranque y comprobación de etapa 1

- Arranque y consultas comprobados sobre el entorno existente.
- El ciclo completo desde detenido no se ejecutó en ese ensayo; detalle histórico en [S05-arranque.md](evidencias/S05-arranque.md).

## HDU-019 · 28/10/2026 · Cuatro preguntas comprobadas desde HTML

- Cuatro preguntas comprobadas en la página, con fuentes del paciente elegido.
- Casos en `datos/preguntas.json`; los campos se bloquean durante la espera y se restauran al terminar.

## HDU-018 · 28/10/2026 · Espera y reintento en el chatbot

- El chatbot muestra espera, valida pregunta vacía y permite reintentar errores.
- Si Ollama no responde, iniciarlo con el helper y repetir la pregunta conservada.

## HDU-017 · 28/10/2026 · Chatbot en el navegador

- Página con selector de pacientes y columnas sin/con RAG.
- Abrir el puerto 8000; la página usa `/patients` y `/chat`.

## HDU-016 · 28/10/2026 · Comparación directa y RAG

- Comparación directa/RAG con misma pregunta, modelo y parámetros.
- `verificar_chat.py` prueba una respuesta documentada y otra ausente. El 503 Qdrant se probó con una API aislada.

## HDU-015 · 28/10/2026 · Respuesta directa del LLM

- Primera respuesta directa con llama3.2:3b; llamada centralizada en `app/llm.py`.
- `POST /chat` envió solo la pregunta en esta HDU; el contexto se incorporó después.

## HDU-014 · 28/10/2026 · Recuperación y persistencia Qdrant

- Recuperación y persistencia Qdrant comprobadas en el ensayo original.
- `verificar_recuperacion.py` coteja los documentos y las búsquedas; conservar ese resultado histórico.

## HDU-013 · 28/10/2026 · Buscar dos fragmentos del paciente

- Búsqueda limitada a dos fragmentos del paciente solicitado.
- `buscar.py ID pregunta`; similitud no significa que los textos contengan la respuesta.

## HDU-012 · 28/10/2026 · Ingesta sin duplicados

- Ingesta de los Markdown con ids estables, sin duplicar puntos al repetirla.
- `ingestar.py` guarda paciente, archivo, sección y texto en Qdrant.

## HDU-011 · 28/10/2026 · Embeddings y colección Qdrant

- Ollama, embeddings de 768 componentes y colección Qdrant preparados tras reanudación autorizada.
- `preparar_vectores.py` comprueba dimensión/Cosine sin borrar colecciones; el mínimo de RAM no se acreditó.

## HDU-010 · 28/10/2026 · Historias y preguntas ficticias

- Tres historias ficticias, nueve secciones y cuatro preguntas preparadas.
- Leer `datos/`; el bloqueo inicial por RAM fue superado por la reanudación de HDU-011.

## HDU-009 · 28/10/2026 · Persistencia Java y repaso de equivalencia

- Persistencia Java comprobada tras reiniciar PostgreSQL y la API.
- `verificar_persistencia.ps1 -Servicio java-api`; Python conserva su tabla separada.

## HDU-008 · 28/10/2026 · Comparar el contrato de las dos APIs

- Contrato Python/Java contrastado; dominio de email Java corregido.
- El verificador común comprueba CRUD y entradas inválidas sin exigir textos 422 idénticos.

## HDU-007 · 28/10/2026 · Editar y borrar pacientes en Java

- Java añadió PUT y DELETE, con transacciones y 404 compartido.
- Usar un temporal propio o ejecutar `verificar_crud.py` contra Java.

## HDU-006 · 28/10/2026 · Crear y consultar pacientes en Java

- Java añadió POST y GET con los mismos campos JSON que Python.
- Ana, Bruno y Carla se cargan desde `datos/pacientes.json`; repetir esa carga manual duplica filas.

## HDU-005 · 28/10/2026 · Spring Boot conectado a PostgreSQL

- Spring Boot conectado a PostgreSQL, con health y tabla `java.patients`.
- Puerto 8080. En este punto aún no había CRUD; se añadió en HDU-006/007.

## HDU-004 · 28/10/2026 · Persistencia y repaso del CRUD Python

- Persistencia Python comprobada; pool_pre_ping descarta conexiones antiguas.
- `verificar_persistencia.ps1` compara antes/después sin borrar el volumen.

## HDU-003 · 28/10/2026 · Editar, borrar y responder errores

- Python añadió PUT, DELETE y 404; verificador de CRUD y errores.
- Usar el recorrido temporal del README; Python quedó fijado en 3.15.2.

## HDU-002 · 27/10/2026 · Crear y consultar pacientes

- Tabla Python, POST/GET y validaciones; tres pacientes ficticios preparados.
- Código en `db.py`, `models.py`, `schemas.py` y `main.py`; el error 500 por id ausente se corrigió en HDU-003.

## HDU-001 · 27/10/2026 · PostgreSQL + FastAPI en Docker

- PostgreSQL y FastAPI en Docker, `.env` local y volumen `pgdata`.
- Inicialmente solo `/health`; [S01.md](evidencias/S01.md) conserva las pruebas y el requisito de RAM no satisfecho.
