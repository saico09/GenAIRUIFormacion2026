# Interfaz · 07/11/2026

Mejora pedida por Marco sobre las APIs existentes. No cambia las HDU, sus horas, las fechas ni los requisitos del plan de Rui.

La página tiene cuatro secciones: **Consultas médicas**, **Pacientes**, **API Python** y **API Java**. Pacientes usa directamente Spring Boot para listar, crear, editar y borrar; Java y Python mantienen tablas separadas. La comparación RAG conserva el mismo endpoint, pregunta, modelo y fuentes. El frontend sigue siendo HTML, CSS y JavaScript sin dependencias externas.

## Comprobaciones

| Prueba | Evidencia |
|---|---|
| Doce bloques: navegación y foco; CRUD real desde la tabla; 200/404/422 de ambas APIs; JSON inválido y cancelación sin enviar; espera y prevención de envíos duplicados; Actuator real; cuatro vistas a 390 px | [Portal](portal-resultados.json) |
| CORS Java: orígenes locales permitidos, origen/cabecera ajenos rechazados, CRUD, validación y conservación de pacientes | [CORS](cors-java.json) |
| CORS de Actuator: health y Prometheus permiten los dos orígenes locales y rechazan el origen ajeno | [Actuator](cors-actuator.json) |
| Cuatro preguntas reales desde el navegador: Alfa, Beta, Gamma y cirugía sin información; texto y fuentes coinciden con la API | [Resultados RAG](chat/resultados.json) · [Salida del ensayo](chat-real.txt) |
| Construcción de ambas APIs | [Build inicial](build-apis.txt) · [Ajuste UI](build-ui-final.txt) · [CORS Actuator](build-java-actuator.txt) |
| Cierre: nueve accesos HTTP, nueve servicios principales, mismos pacientes y nueve puntos Qdrant | [Estado comprobado](main-verificacion-final.json) |

Los errores de red/500 y la prueba rápida de carga del chat del verificador del portal son **simulados en el navegador**. El ensayo RAG separado sí ejecuta el modelo y Qdrant reales. El primer intento obtuvo 503 porque Ollama estaba apagado; se inició con `scripts/iniciar_ollama.ps1` y después pasaron las cuatro preguntas.

La revisión corrigió la respuesta anterior visible al editar una petición y la configuración CORS separada de Actuator. También se conserva el foco al abrir la edición y al saltar al contenido sin cambiar de sección. Se mantuvieron los cuatro pacientes Python y los tres Java con hashes idénticos. Las capturas de escritorio y móvil están en esta carpeta; las cuatro respuestas reales, en `chat/`.

## Repetir

Con las APIs levantadas, para CORS Java:

```powershell
python java-api/src/test/python/verificar_cors.py --base-url http://127.0.0.1:8080 --origin http://localhost:8000 --origin http://127.0.0.1:8000
```

Para la interfaz, con Node, Playwright y Edge disponibles:

```powershell
$env:EVIDENCE_DIR = "ejecuciones/ui-$([guid]::NewGuid().ToString('N'))"
node scripts/verificar_portal_ui.cjs
```

Para las cuatro preguntas reales, con Ollama y Qdrant disponibles:

```powershell
$env:EVIDENCE_DIR = "ejecuciones/rag-ui-$([guid]::NewGuid().ToString('N'))"
node scripts/verificar_chat_ui.cjs --dataset
```

Las pruebas CRUD crean y eliminan solo sus temporales y comparan los registros anteriores. No edites pacientes durante el ensayo. `CHAT_URL` y `JAVA_URL` permiten apuntar el verificador del portal a una copia semanal.

## Entregas

La adaptación corresponde a S4–S10, desde la aparición del chatbot HTML. S1–S3 conservan su cierre original. Las métricas se ofrecen desde S6; no se añaden servicios de semanas posteriores. Los puertos, comandos y resultados de cada copia se guardan fuera del repo, en `dailys/`, junto con sus guiones y procedencia. S6 sigue sin daily y se presenta junto con S7.

Pasaron **las siete copias**: 140 comprobaciones CORS, 82 bloques del portal y siete comprobaciones finales de archivos servidos y foco. Cada una conservó tres pacientes Python y tres Java; quedaron detenidas. En esas copias solo se iniciaron PostgreSQL y ambas APIs: el chat del ensayo es simulado, no se repitió el RAG real semanal ni Minikube. [Resumen de las copias](semanas-resumen.json); el detalle local está en `dailys/UI_VERIFICADA_2026-11-07.json`.

Se actualizaron seis Word existentes en Drive (S4, S5, S7–S10), conservando sus IDs y verificando el texto remoto. Los guiones de S1–S3 y el aviso de S6 permanecen iguales. Las notas de Trello en 008, 017 y 018 enlazan la implementación `0c690ef`; no modifican criterios, fechas ni estado.

La revisión personal y la evaluación de Rui siguen pendientes. Estas pruebas acreditan funcionamiento técnico, no reuniones ni horas realizadas.
