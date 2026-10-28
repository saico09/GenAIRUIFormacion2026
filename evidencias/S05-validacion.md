# HDU-024 · Preparación comprobada · 28/10/2026

**Validación pendiente.** No se ha recibido confirmación de sesión, explicación personal de Marco ni valoración de Rui. El trabajo técnico se adelantó por solicitud del usuario; no acredita horas personales ni cambia la fecha objetivo del 27/11.

| Comprobación previa | Resultado real | Evidencia |
|---|---|---|
| Health Python y Java | 200 en ambas | [Preflight](S05/024-preflight.json) |
| Ana en ambas APIs | 200, id 1 y los cuatro campos originales | [Preflight](S05/024-preflight.json) |
| HTML, enfermedad de Ana | Alfa y cita de paciente-1.md/Enfermedad | [Captura](S05/024-caso-1.png) |
| HTML, última cirugía | No hay información suficiente | [Captura](S05/024-caso-2.png) |

[Respuestas y fuentes completas](S05/024-resultados.json). La prueba del navegador terminó con código 0 y conservó la misma pregunta y modelo entre las dos ramas. Para repetir, usa el [guion](S05-guion.md), ya [ensayado](S05-ensayo.md).

Las seis frases del ensayo son apoyo para entender PostgreSQL y el recorrido RAG; no sustituyen las tres frases propias ni demuestran comprensión de Marco. Falta que él explique por qué persisten los pacientes, qué recupera Qdrant y qué aporta el prompt.

No hay valoración 1–4 ni correcciones expertas recibidas. Se corrigió y repitió la espera de disponibilidad durante el ensayo: `scripts/esperar_apis.ps1` evita consultar una API que todavía arranca. El ciclo completo desde detenido de HDU-020 sigue NO EJECUTADO por el rechazo automático anterior a detener Qdrant. Las tarjetas se mantienen abiertas en Testing; estas evidencias y el guion se guardan en el commit conjunto 020–024.
