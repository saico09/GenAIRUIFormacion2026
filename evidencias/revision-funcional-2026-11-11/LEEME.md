# Revisión de funciones y síntomas breves · 11/11/2026

La pestaña de Marco seguía mostrando un documento de la interfaz antigua. El servidor tenía el portal completo. Al recargar esa misma pestaña reaparecieron Consultas, Pacientes, API Python y API Java; se conservó el texto que Marco había escrito, sin enviarlo otra vez. No se atribuye esto a una reversión de Git ni a un fallo de caché demostrado.

La consulta `dolor de estómago agudo` sí había llegado al backend nuevo y estaba guardada en el Markdown y PostgreSQL. El modelo eligió orientación de síntomas, pero aplicó indebidamente la instrucción de malestar inespecífico. Se aclaró el prompt: un síntoma concreto breve admite causas posibles y condiciones que las apoyarían; los detalles faltantes se sugieren al final. Las posibilidades no se convierten en antecedentes confirmados.

Se agrupó recuperación → RAG → respuesta directa → guardado para evitar una alternancia entre el modelo de embeddings y el de chat. Se conservan la misma pregunta y modelo en las dos ramas. Los logs incorporan tiempos nativos de carga, procesamiento y generación, en milisegundos; un dato ausente queda en `null`.

La configuración usa **`qwen3.5:4b-q4_K_M`, temperatura 0.2 y `think=false`**. La fuente funcional final es `e8b2ceb903331b2d860fe1c5fc8fc5a06e44fdc1`; las inferencias se realizaron sobre `9723f942`, antes del último ajuste del validador descrito abajo. En este equipo el modelo ocupó unos 3.36 GB y entró completo en la GPU; Gemma 12B repartía el modelo entre GPU y RAM. Ollama sigue siendo el servidor. La respuesta de orientación llega como causas, condiciones hipotéticas y detalles opcionales; Python valida esos campos y los convierte en texto. No hay un catálogo de diagnósticos prefabricados ni una segunda llamada para corregir cada respuesta. Los prompts están en `python-api/rag.py` y el formato compartido, en `python-api/orientation.py`.

Comprobaciones disponibles:

- `ui-recuperacion.json`, `pacientes-recuperados.jpg`: documento antes/después y portal real del navegador integrado. GET de salud desde ambos exploradores: 200.
- `assets-http.json`, `revision-ui-fuentes.md`: 20 lecturas HTTP y contraste con la fuente; no se retiraron los módulos del portal.
- `backend-crud-cruzado.json`, `BACKEND.md`: 29 peticiones y 21 comprobaciones de CRUD cruzado, MD automático, respaldo SQL y auditoría. Temporal 57 eliminado; cinco pacientes y sus archivos conservados.
- `offline-alerta-puntuacion.json`: 95 pruebas offline con el código final. `paridad-alerta-puntuacion.json`: 54 comprobaciones de coincidencia entre JSON Schema y el validador. Los reportes offline anteriores son cortes intermedios. `backend-unificacion-offline.json`: otros 22 contratos de CRUD compartido, con la red bloqueada.
- `revision-codigo-independiente.json`: revisión de aislamiento de preguntas, persistencia, citas y trazas.
- `latencia-diagnostico.json`: medición anterior de 126,2 s para el caso reportado; no es una comparación controlada de rendimiento.
- `ui-guardado-sql.json`, `chat-final.jpg`: consulta real desde la página, «dolor de estómago», con ambas respuestas en 24,46 s; Markdown y SQL coinciden. Reintento con el mismo UUID sin duplicar ni confirmar hipótesis.
- `ui-agudo-sql.json`, `ui-chat-agudo.txt`, `historia-dos-consultas.jpg`: segunda consulta real, «dolor de estómago agudo», con el código final, HTTP 200 en 22,32 s. La ficha muestra ambas consultas, sus textos coinciden con Markdown/SQL y conserva un solo registro confirmado.
- `regresion-http-final.json`, `regresion-traza.json`: cuatro consultas HTTP reales (16,71 / 12,75 / 16,20 / 14,11 s), reintento, conflicto 409, propuestas afirmada/negada y una quinta consulta con cinco spans Phoenix y siete eventos Loki. Se cotejaron respaldo, UUID y `patient_id`; el índice no incorporó las respuestas generadas. El temporal 59 se eliminó y los cinco pacientes originales conservaron sus historias y vectores.
- `ui-temporal-58-limpieza.json`, `ui-cierre.json`: eliminado el temporal del navegador y sus vectores; se conservaron sus respaldos y auditoría. La pestaña quedó con Ana y el borrador original, sin reenviarlo.

Los tiempos son muestras de este equipo, con tamaños de respuesta y estado de carga distintos; no son una garantía de latencia ni un benchmark controlado.

## Lo que todavía limita las respuestas

El formato correcto no demuestra que una alternativa sea pertinente. `revision-lecturas-finales.json` y `revision-regresion-http.json` conservan la revisión manual: con un relato muy vago aparecieron asociaciones poco útiles y, para dolor de cabeza, una alternativa tautológica («cefalea si hay dolor en la cabeza»). Los relatos largos de reflujo reciben orientación, pero aún pueden repetir detalles ya entregados o usar términos técnicos. No se presenta esta muestra como precisión diagnóstica general.

Se conservaron los ensayos descartados: Gemma lento (`agudo-lectura.json`), Qwen 3 con premisas inventadas y Qwen 3.5 libre con preguntas o atributos de notas anteriores. El primer ensayo estructurado rechazado no conservó la respuesta cruda; el verificador se corrigió para capturarla antes de validar. Otra prueba rechazó una alarma parafraseada: `relatos-alarma-final-lectura.json`. El esquema final ofrece citas literales de la consulta; `alarma-enum-literal-lectura.json` pasó ambas ramas. La clasificación semántica de una alarma sigue a cargo del modelo, no de un diagnóstico determinista.

Una revisión posterior encontró otro defecto del validador: la puntuación final o una segunda frase podían ocultar una negación al revisar sólo la última cláusula. La corrección revisa toda la cita y su prefijo tanto al generar el esquema como al validar. `guard-alerta-fallo-previo.json` conserva el fallo; `guard-alerta-revision-independiente.json` pasó 11 controles. `replay-guardia-final.json` pasó cuatro respuestas crudas anteriores (alarma y traza): esquema válido y texto renderizado idéntico, con la red bloqueada, sin nueva inferencia ni HTTP. Conserva un límite conocido: una cita que mezcla una afirmación con una negación ajena puede rechazarse de forma conservadora. No es un clasificador clínico general. Las inferencias y las pruebas HTTP anteriores preceden a este último ajuste determinista.

## Entregas semanales

S4–S10 incorporan la fuente funcional final `e8b2ceb`, conservando su etapa: S4–S7 coordinan directamente y S8–S10 mantienen LangGraph. Pasaron 420 pruebas offline (60 por copia) y siete revisiones estáticas después de la corrección de la guarda. El corte previo `9723f942` tuvo 406 pruebas (58 por copia) y queda conservado en `entregas-9723f94.json`. Sobre ese corte se ejecutaron los coordinadores S4/S8 con cuatro respuestas del modelo real y recuperación fija; esto no acredita otro arranque de sus pilas Compose ni pruebas de HTTP/SQL/MD/Qdrant/GitOps semanales. El resumen final y la conservación están en `entregas.json`.

La revisión manual semanal fue parcial: S4 no citó los antecedentes disponibles en esa orientación y usó una sensación como causa; S8 sí citó los tres fragmentos, pero ofreció alternativas con condiciones poco específicas. También hubo repetición de detalles y puntuación doble. Los reportes separan integración correcta de pertinencia semántica.

Se conservaron 1.977 archivos, incluidos S1–S3, las interfaces, Java, los datos de pacientes y la configuración privada. Los 20 DAILY Markdown/Word conservaron sus huellas: los guiones ya explican la comparación y las hipótesis sin depender del nombre del modelo, por lo que no se reescribió Drive ni se afirma una nueva lectura remota. Se mantiene S6+S7. `LEVANTAR.txt` sigue breve, con los puertos 8000/8080; `CONSULTAS.md` señala dónde cambiar el prompt.

## Entorno al cerrar

`cierre-entorno.json` pasó ocho bloques de lectura sin reintentos: cinco pacientes, cinco Markdown y tres registros confirmados intactos; todas las filas SQL anteriores conservadas; 16 puntos Qdrant con los mismos IDs, payloads y vectores. La tabla de logs mantiene un solo UUID `id` y `patient_id`. Los temporales 57, 58 y 59 quedaron eliminados, conservando los respaldos y logs históricos previstos por la aplicación.

Quedaron once contenedores activos, como al empezar. Sólo se recreó Python; los otros contenedores conservaron su inventario. Las copias semanales y Minikube siguen detenidos. Los nueve accesos HTTP devolvieron 200 y los dos targets de Prometheus estaban UP. Se cotejaron 34 archivos servidos con la fuente local y la configuración final de Qwen. No hubo otro reinicio global de Docker/WSL ni ensayo nuevo de Minikube.

La referencia para revisar las alternativas digestivas y sus condiciones es [NHS: stomach ache](https://www.nhs.uk/symptoms/stomach-ache/). Las métricas proceden de [Ollama Generate](https://docs.ollama.com/api/generate); la distribución en memoria se inspecciona con [Ollama ps](https://docs.ollama.com/faq#how-can-i-tell-if-my-model-was-loaded-onto-the-gpu). Son pruebas acotadas de una capacitación con pacientes ficticios, no una evaluación clínica general.

Para repetir sólo contratos, sin consultas al modelo ni datos vivos, sigue los comandos guardados en `offline-alerta-puntuacion.json`. Para repetir un caso de lectura con el modelo configurado:

```powershell
python -B scripts/verificar_sintomas_breves.py --execute --cases agudo --patient-id 1 --output .local/sintomas-breves.json
```

Ese ensayo no llama a `/chat` ni guarda consultas; comprueba las huellas del índice y los Markdown antes y después.
