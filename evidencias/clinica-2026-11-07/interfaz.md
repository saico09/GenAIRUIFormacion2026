# Interfaz clínica · 07/11/2026

El recorrido completo pasó con servicios y LLM reales, sin mocks: [resultado](ui-llm-real-final/resultados.json). Se usó únicamente el paciente temporal Java 31, ausente de la tabla Python.

| Paso | Resultado comprobado |
|---|---|
| Preparar con IA | La nota explícita produjo Nube / Clara / Azul, con las tres citas literales. La respuesta HTTP completa y los campos propuestos están en el JSON. |
| Revisar y confirmar | Cancelar no escribió. Confirmar guardó un registro con UUID `c4f3e2e7-f370-43fc-9d41-21edc73c5f0a`; los campos confirmados también quedaron registrados. |
| Descargar y editar | Descarga idéntica al Markdown. Editar Nube → Cedro conservó el UUID, cambió la revisión y sincronizó el índice. [Archivo posterior](ui-llm-real-final/historia-editada.md). |
| Preguntar | RAG respondió «Síndrome ficticio Cedro» y citó ese archivo, UUID y sección. La consulta no cambió el informe. |
| Preparar registro desde el chat | Sólo llevó la pregunta al borrador; no archivó la respuesta. |
| Renombrar y eliminar | El nombre de archivo cambió y conservó el UUID. La eliminación retiró los fragmentos del temporal. |

Propuesta: request_id `a21fff12-558f-464c-a710-de1a6c443cb7`. Chat: `b169189b-6792-46e6-b446-162dd5751cc2`. Ambos permiten localizar las llamadas originales al modelo; el JSON del test conserva la respuesta de la API, no sustituye esos logs.

Capturas inspeccionadas: [historia editada](ui-llm-real-final/historia-editada.png) y [consulta con su fuente desplegada](ui-llm-real-final/consulta.png). Sin recortes ni solapamientos. La prueba terminó a las 21:54:04 UTC; eliminó su temporal y comprobó los mismos hashes completos de cuatro pacientes Python, tres Java y tres informes previos.

El [primer intento](ui-llm-real/resultados.json) se conserva: la propuesta quedó vacía porque el modelo reformuló las citas de evidencia. No se guardó nada y su temporal también se limpió. La corrección obtiene la evidencia literal desde la nota en el servidor; el ensayo final anterior pasó después de ese cambio.

También pasaron:

- [Nueve escenarios aislados](ui-aislada/resultados.json): APIs simuladas, confirmaciones, 422/409, borrador conservado, reintento del índice, campos manuales y seis nuevas rutas de los exploradores.
- [Doce comprobaciones del portal](portal-regresion/portal-resultados.json): CRUD y CORS reales; chat y fallos de red simulados explícitamente, cuatro vistas móviles sin desbordamiento y datos previos conservados.
- [Integración inicial](ui-integracion/resultados.json): Java, Markdown e índice reales; sólo propuesta y chat simulados.

Para repetir desde `codigo/`, usa una carpeta nueva de evidencias y deja libre el modelo durante el ensayo:

```powershell
$env:NODE_PATH='C:/Users/marco/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
```

```powershell
$env:EVIDENCE_DIR=Join-Path (Get-Location) ('evidencias/clinica-2026-11-07/ui-real-' + [guid]::NewGuid().ToString('N'))
```

```powershell
& 'C:/Users/marco/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' scripts/verificar_historia_ui_real.cjs --real-llm
```

El script crea y elimina sólo su paciente marcado; no inicia ni detiene servicios. Estas pruebas técnicas no acreditan una revisión de Rui ni calidad clínica general.
