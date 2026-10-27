---
name: guia-e-historial
description: Actualiza GUIA.md (comandos para usar la app) e HISTORIAL.md (qué se fue agregando) al terminar cada HDU de este proyecto, con el estilo informal que pidió Marco. Usar cada vez que se cree o cambie algo usable de la app (servicio, endpoint, comando, archivo de datos).
---

# Guía e historial

Marco quiere guías cortas e informales, solo para él. Nada de instructivos formales salvo que lo pida.

## GUIA.md

- Una línea en minúscula que diga para qué sirve, y debajo el comando en su propio bloque ```bash (un comando por bloque).
  Ejemplo: `levantar postgres:` + bloque con `docker compose up -d postgres`.
- Agrupar con `##` cortos por tema (Levantar / bajar, Postgres, python-api, Logs...).
- Añadir solo comandos que funcionan hoy y que se probaron. Si un comando cambia, se reemplaza; no se acumulan versiones viejas.
- Avisar con "ojo" cuando algo borra datos.

## HISTORIAL.md

- Una sección por HDU, la más nueva arriba: `## HDU-XXX · dd/mm/aaaa · título corto`.
- 3 a 7 viñetas: qué es cada pieza nueva y cómo se usa en una frase. Sin pegar comandos largos (esos van en GUIA.md).
- Decir lo que todavía NO hace si se puede confundir, y anotar riesgos o pendientes en una viñeta "Ojo".

## Reglas

- Español, tono cercano, frases cortas.
- No inventar cosas no implementadas ni marcar como hecho lo que no se probó.
