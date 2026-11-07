# A/B de fundamentación · 07/11/2026

Se ejecutaron 24 llamadas RAG secuenciales: seis casos ficticios de Ana Demo por cuatro variantes. Mismo `llama3.2:3b`, temperatura 0, contexto 2048 y máximo 256 tokens. No se cambió la aplicación ni se escribieron datos clínicos. Las 24 respuestas terminaron por `stop`, sin truncamiento por longitud.

Los [prompts, fragmentos y respuestas originales](ab-fundamentacion-rag.json) conservan la evaluación automática inicial. La [lectura manual separada](ab-lectura-manual.json) revisa cada respuesta completa: distingue contenido incorrecto de un formato distinto. No reemplaza ni corrige la salida del modelo.

| Variante | Abstenciones sin falsa fuente | Tres hechos y sus citas | Control literal | Casos correctos por contenido |
|---|---:|---|---|---:|
| Top2 + prompt actual | 2/4 | Incompleto | Correcto | 3/6 |
| Top2 + alternativo | 2/4 | Incompleto | Correcto | 3/6 |
| Top3 + actual | 2/4 | Correcto | Correcto | 4/6 |
| Top3 + alternativo | 4/4 | Correcto | Correcto | 6/6 |

El chequeo automático obtuvo 3/6, 1/6, 3/6 y 2/6 respectivamente. Exigía la abstención literal y una pareja respuesta/cita por hecho. Algunas respuestas explican que falta información sin inventar nada, y las respuestas múltiples agrupan tres citas válidas: son diferencias de formato. Las citas a fragmentos que no contienen los síntomas y la atribución de un medicamento al dolor sí son fallos de contenido, y siguen marcados como tales.

Top2 dejó fuera Tratamiento en la consulta múltiple. Recuperar tres fragmentos resolvió esa cobertura, pero el prompt actual siguió produciendo falsas citas. El alternativo con tres fragmentos fue mejor en estos seis casos; **una muestra de seis no demuestra una solución general**. El prompt y top2 de producción permanecen iguales; top2 forma parte de las HDU-013/016.

Para repetir este experimento aislado desde `codigo/` (PowerShell 7):

```powershell
Get-Content -Raw -Encoding utf8 scripts/experimentar_fundamentacion_rag.py | docker compose exec -T python-api python - --output /tmp/ab-fundamentacion-rag.json
docker compose cp python-api:/tmp/ab-fundamentacion-rag.json ejecuciones/ab-fundamentacion-rag.json
```

Usa una salida nueva para cada ensayo. El script conserva cada llamada de forma incremental. La valoración manual no se genera automáticamente ni cambia al repetirlo.
