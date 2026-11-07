# Revisión del RAG · 07/11/2026

La observación de Marco se confirma: la carga de documentos funciona, pero eso no garantiza respuestas útiles ni bien fundamentadas. Dos de las cuatro consultas recientes produjeron una respuesta sin respaldo: una presentó síntomas de la pregunta como si estuvieran documentados; otra devolvió Medicamento Alfa sin que el documento lo relacionara con el síntoma. Ambas llevaban una cita. Esos comportamientos se reprodujeron en el experimento aislado.

## Qué encontramos

- La historia de Ana tiene sólo tres hechos: Enfermedad Alfa, Tratamiento Alfa y Medicamento Alfa. No contiene síntomas, dosis, evolución ni consultas anteriores. Es un corpus mínimo de demostración.
- Qdrant conserva los nueve fragmentos correctos de los tres Markdown; no falta una ingesta. [Inventario comprobado](almacenamiento.json).
- El buscador entrega siempre dos fragmentos. Si se piden los tres hechos de Ana, uno queda fuera del contexto. El prompt actual también está orientado a un dato y una fuente.
- La pregunta puede contaminar la respuesta: el modelo llegó a repetir síntomas introducidos por el usuario y atribuirlos a un archivo que no los contiene. Tener una cita no demuestra que esa cita respalde lo dicho.
- Las pruebas anteriores eran demasiado estrechas: comprobaban cuatro preguntas preparadas, presencia del texto esperado y coincidencia entre pantalla/API. No evaluaban adecuadamente afirmaciones sin respaldo ni la relación entre pregunta, hecho y cita.

Las doce consultas nuevas a `/chat` dieron seis respuestas correctas a hechos concretos, dos resúmenes incompletos y cuatro abstenciones; una de estas últimas añadió una cita que no respaldaba un hecho. [Resultados completos](experimento.json). La fecha de nacimiento existe en SQL, pero no se entrega al modelo: en esa pregunta la abstención era coherente con el contexto que recibió.

En un A/B aislado se mantuvieron modelo y parámetros, combinando dos/tres fragmentos con el prompt actual/alternativo: seis casos y 24 respuestas. Tres fragmentos por sí solos no eliminaron las citas falsas. El prompt alternativo con tres fragmentos respondió adecuadamente los seis casos revisados, incluidas las abstenciones y el resumen de los tres hechos. Es una muestra pequeña y una ejecución por variante, no una garantía general. [Salidas originales y chequeos de formato](ab-fundamentacion-rag.json) · [Valoración manual separada](ab-lectura-manual.json).

## Dónde se guarda cada cosa

| Lugar | Contenido actual |
|---|---|
| PostgreSQL, `public.patients` y `java.patients` | ID, nombre, fecha de nacimiento y email. Los dos CRUD mantienen registros independientes. |
| `datos/paciente-*.md` | Documentos clínicos ficticios escritos previamente. Son la fuente de la ingesta; preguntar no los modifica. |
| Qdrant, colección `historias` | Embeddings y copias de los fragmentos, con paciente, archivo, sección y texto. RAG busca aquí al responder. |
| Loki y Phoenix | Logs y trazas de ejecución, con prompts/respuestas. Sirven para inspeccionar el sistema; no se usan como memoria del chat. |

No hay una entidad de atención médica, una agenda ni un historial conversacional en PostgreSQL. Cada pregunta se procesa de forma independiente. El plan original pide el CRUD de datos básicos en PostgreSQL y el conocimiento clínico en la base vectorial; Markdown es una opción admitida. Gestionar atenciones o conversaciones persistentes sería una ampliación, no un requisito omitido.

## Qué conviene corregir

1. Hacer las historias ficticias más completas, conservando información explícita y comprobable.
2. Distinguir en el prompt los hechos del documento de los síntomas o supuestos escritos en la pregunta; no inferir diagnósticos ni medicación sin una relación documentada.
3. Recuperar contexto suficiente para preguntas compuestas y respaldar cada afirmación. El TOP2 figura expresamente en HDU-013/016: cambiarlo requiere registrar la adaptación de esos criterios, aunque Rui no impone ese número.
4. Añadir casos de regresión con paráfrasis, síntomas ausentes, varios hechos y citas incorrectas. Mostrar el fragmento citado ayudaría a revisar la respuesta.

El código de la aplicación, los documentos clínicos y las copias semanales **no se modificaron** en esta revisión. El prompt alternativo sólo existe en el script de experimento. No se ha dado por corregida la fundamentación del RAG.

Para repetir las doce consultas, desde `codigo/`, con el entorno ya levantado:

```powershell
python scripts/diagnosticar_rag.py --output "ejecuciones/rag-$([guid]::NewGuid().ToString('N')).json"
```

Para repetir el A/B, guarda primero una ruta distinta dentro del contenedor:

```powershell
$ensayo = "/tmp/rag-ab-$([guid]::NewGuid().ToString('N')).json"
Get-Content -Raw scripts/experimentar_fundamentacion_rag.py | docker compose exec -T python-api python - --output $ensayo
docker compose exec -T python-api cat $ensayo
```

Los chequeos automáticos del A/B son intencionalmente estrechos y se conservan sin convertir diferencias de formato en afirmaciones de calidad general. Revisa siempre las respuestas y sus fuentes.
