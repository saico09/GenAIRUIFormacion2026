# Revisión del 12/11/2026

Fuente funcional: `6173af2`. Se conservan las cuatro secciones del portal, pacientes compartidos, CRUD de registros, informes Markdown, consultas y auditoría SQL, comparación RAG y observabilidad.

| Cambio | Comprobación |
|---|---|
| Java: validaciones de correo y lectura del Markdown | 7 pruebas JUnit, casos adversos y 50.000 correos sintéticos comparados con la validación anterior |
| Interfaz: esperas de operaciones e íconos alineados | 8 contratos Node y recorrido real del navegador, incluyendo una comparación con Ollama |
| Helm: token desactivado y almacenamiento efímero declarado | `helm lint` y comparación del manifiesto renderizado; sólo cambian tres campos |
| Pruebas reutilizables | Assets HTTP, CRUD cruzado y conexión Minikube aislada en `scripts/` |
| Limpieza | Históricos archivados fuera del proyecto, con huellas verificadas; no se borraron los datos |

## SonarQube

Análisis terminado correctamente: **49 → 29 avisos**. Son 21 correcciones en código conservado, un aviso que sale al archivar un experimento obsoleto y dos avisos nuevos de pruebas/verificadores. No quedaron avisos abiertos en los archivos de runtime y Helm analizados.

Se conservan 24 avisos sobre `assert` capturados por reportadores que registran el fallo y terminan con error, tres sobre TLS autofirmado de Argo local, uno del patrón antiguo usado como referencia en una prueba y otro por comprobar assets vía HTTP de localhost. No ejecutar los verificadores con `python -O`.

El **Quality Gate sigue en ERROR**: cobertura importada 0 % y 23 incidencias de código nuevo. No se importaron reportes de cobertura ni se modificaron reglas, umbrales o estados de los avisos. El analizador advierte límites con Python 3.15/Java 27 y bibliotecas JUnit no configuradas para el análisis de tests. [Comparación](comparacion-sonar.json), [decisiones y límites](revision-final-sonar.json).

El primer análisis incluía los cambios visuales de dos archivos sobre `c2ee267`; el segundo coincide con `6173af2`. Un ajuste posterior del verificador de inventario excluye contenedores de pruebas efímeros: está revisado, pero fuera del snapshot de Sonar.

## Entregas semanales

Se adaptaron diez copias: Java desde S2, interfaz desde S4 y Helm desde S9. S1 sólo recibe guías simplificadas. Pasaron 56 contratos Node y 49 controles de sintaxis; 3.105 archivos ajenos a los cambios permanecieron intactos. Los 20 DAILY/Word, datos, `.env`, puertos y LEVANTAR se conservaron. No hubo cambios de contenido en Drive.

La comprobación semanal fue offline y estática; no se levantaron sus pilas completas, JVM semanales ni Minikube. No cambia el calendario, las HDU ni las revisiones humanas.

## Resultado funcional

Pasaron 107 comprobaciones Python offline (53 unittest, 32 de historia y 22 de unificación), 7 JUnit, 8 contratos Node, 20 lecturas HTTP de assets, 29 peticiones del CRUD compartido con 21 controles y 14 bloques del navegador real. La prueba de chat usó un paciente temporal: RAG citó rinitis/cetirizina, la rama directa indicó que no tenía antecedentes y ambas respuestas quedaron guardadas. Los tres temporales 60, 61 y 62 se retiraron; sus logs y respaldos se conservan por diseño.

El [cierre de lectura](cierre-entorno-final.json) pasó 10/10: cinco pacientes, tres registros confirmados, cinco Markdown, todas las filas SQL previas y 18 puntos Qdrant intactos. Nueve accesos HTTP y dos targets Prometheus correctos. Sólo se recrearon Python y Java; los otros servicios conservaron sus contenedores.

El primer CRUD pasó sus operaciones pero su verificador confundió un runner efímero con un cambio de servicios; se corrigió ese inventario y se repitió completo. El primer cierre recibió un 503 de Loki; después volvió a 200 sin reinicio, con causa interna no determinada. Ambos intentos se conservan. No se ejecutó Minikube ni se presenta esta muestra como validación clínica general.

Trello recibió sólo comentarios en HDU-008, 017 y 040. Se releíyeron tres tarjetas, cuatro checklists y 19 pasos sin cambiar fechas, estados ni marcas. Los guiones y Word de Drive no necesitaron cambios de contenido.

## Archivos de esta revisión

`sonar-antes/` y `sonar-despues/` contienen los resultados del servidor. `java-validacion.json`, `frontend-sonar.json`, `helm-validacion.json`, `python-*.txt/json` y `ui-validacion.json` registran las pruebas acotadas. Los manifiestos `limpieza-*.json` permiten localizar lo archivado. Se conservan los intentos fallidos con su causa; no se presentan como pruebas aprobadas.
