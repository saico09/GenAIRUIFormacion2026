# Comprobación de la interfaz servida · 11/11/2026

Fuente revisada: `a5228c4629588c291ccf86ab64896e17f4c3204f`. Esta inspección fue de lectura; no modificó la aplicación, no ejecutó el modelo ni escribió datos clínicos. La revisión del navegador integrado se registra por separado.

El cambio de `7d591ce` a `a5228c4` sólo añade al HTML la frase de espera del modelo local. Conserva los colores, CSS, navegación y los seis módulos JavaScript. No hay bundle generado, framework de frontend ni service worker: el servidor entrega HTML/CSS y módulos ES directamente desde `python-api/app/static/`.

`assets-http.json` conserva 20 GET de lectura, para `localhost` y `127.0.0.1`: `/`, `/ui-config` y los ocho archivos estáticos. Todos respondieron 200. HTML, CSS y módulos coinciden byte por byte con los archivos locales. El MIME JavaScript es `text/javascript`; la configuración indica Java en 8080 y métricas disponibles. La presencia del código no se toma por una nueva prueba del CRUD en el navegador.

| Pieza | Comprobación de fuente |
|---|---|
| Navegación | Cuatro enlaces, en orden: Consultas, Pacientes, API Python, API Java. `ui.js` alterna `hidden` según el hash y no elimina secciones. |
| Inicio | Importa chat/pacientes/explorador, configura navegación y consulta `/ui-config`. Un error de configuración se muestra en `#config-error`; no retira la barra ni el CSS. |
| Pacientes | Tabla de pacientes; detalle con registros confirmados, CRUD, consultas guardadas y Markdown editable con confirmación. |
| Exploradores | `explorer.js` contiene operaciones Python/Java y CRUD de enfermedades. La inicialización agrega sus controles al DOM tras obtener la configuración. |
| Colores | CSS conserva GET azul, POST verde, PUT ocre, DELETE rojo; errores HTTP y avisos tienen clases diferenciadas. |
| Documento antiguo | El título «Comparar respuestas · GenAI», encabezado «Una pregunta, dos respuestas» y botón «Consultar» corresponden a la interfaz de `1de911a`, con CSS/JS inline. No corresponden al HTML servido en esta inspección. |

## Caché y propuesta mínima

- `/` envía `Cache-Control: no-cache` desde la mejora `0c690ef`. La petición con el ETag actual vuelve a recibir 200 y el mismo cuerpo actualizado; este `FileResponse` no devuelve 304.
- Los archivos `/static/*` tienen ETag/Last-Modified, pero no `Cache-Control` explícito. La revalidación con su ETag vigente devuelve 304. No se observó un asset viejo en las peticiones directas.
- El documento antiguo `1de911a` se entregaba sin `Cache-Control` explícito. Eso no permite deducir si la vista concreta se mantuvo en memoria, se restauró o salió de una caché: falta observar la navegación/recarga del navegador del usuario.
- Una página ya abierta puede seguir mostrando su HTML y ejecutando su JavaScript antiguo contra el backend actualizado. Las cabeceras HTTP no fuerzan por sí mismas a recargar una vista existente. [RFC 9111, sección 4.2](https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2), [sección 6](https://www.rfc-editor.org/rfc/rfc9111.html#section-6).
- Si la recarga del navegador recupera el portal, la solución mínima es conservar el código y añadir una indicación breve de recarga después de actualizar o cambiar de semana. No hace falta polling ni reconstruir la interfaz. `no-cache` obliga a validar una representación cuando se vuelve a solicitar, no a reemplazar espontáneamente el documento mostrado. [RFC 9111, sección 5.2.2.4](https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.4).
- Como mejora preventiva independiente podría fijarse `no-cache` para todos los assets y `/ui-config`; no se presenta como causa ni arreglo acreditado de este incidente. Añadir una versión sólo al `src` de `ui.js` dejaría sin versionar sus imports relativos.

La inspección posterior del agente coordinador mediante CUA en la pestaña real de IAB comprobó la recuperación al recargar: volvieron las cuatro secciones, cinco pacientes y el detalle de Ana con un registro confirmado y siete consultas. Se confirma un documento antiguo que seguía cargado; no se cambió la UI para recuperarlo. Este resultado del navegador procede de esa inspección del coordinador, no de las peticiones HTTP del script de esta carpeta. Se añadió únicamente la indicación de recarga a `GUIA.md`.

## Alcance conservado

Se leyó directamente el PDF original `Programa de Habilitacion GenAI Interno (RAG y Observabilidad).pdf`, páginas 4 y 6. S1 pide CRUD Python/PostgreSQL; S2, API equivalente en Java; S3, documentos clínicos en Qdrant; S4, chatbot HTML y la misma pregunta/modelo con respuestas lado a lado. No establece un diseño visual obligatorio ni prohíbe navegación, tablas o colores. La extracción auxiliar de la reunión, P0017–P0023, conserva el margen del dominio y el flujo HTML → Python → contexto → LLM.

El usuario pidió expresamente la mejora visual, exploradores de ambas APIs, pacientes como segunda sección usando Java, detalle por paciente, Markdown y CRUD de enfermedades. Esas ampliaciones están documentadas en `CONTEXTO_PROYECTO.md`, apartados «Interfaz y uso directo de Java», «Historias clínicas confirmadas» y «Pacientes compartidos». La petición posterior de hipótesis no revoca esas funciones. Retirarlas no era necesario para respetar el plan de Rui; deben mantenerse como ampliaciones personales, sin atribuirles nuevas HDU u horas del plan original.
