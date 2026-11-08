# Casos para probar el RAG

Son personas, fechas y evoluciones inventadas para esta capacitación. Las enfermedades, tratamientos y medicamentos tienen nombres reales. Los tres UUID originales se conservan; cada uno asocia enfermedad, tratamiento y medicamento.

| Paciente | Enfermedad del caso | Tratamiento registrado | Medicamento registrado |
|---|---|---|---|
| Ana Demo | Reflujo gastroesofágico (ERGE) | Evitar desencadenantes y cenas abundantes, dejar tres horas antes de acostarse, registrar episodios y revisar síntomas | Omeprazol |
| Bruno Demo | Diabetes mellitus tipo 2 | Plan de alimentación, actividad física, seguimiento de glucosa y control de HbA1c/función renal | Metformina |
| Carla Demo | Rinitis alérgica estacional por polen | Reducir exposición al polen, lavados nasales con solución salina y seguimiento de síntomas | Cetirizina |

Para probarlos, abre **Consultas médicas**, elige al paciente y pregunta:

- Ana: «¿Qué enfermedad tiene Ana Demo?» y «¿Qué cambios de hábitos tiene registrados para el reflujo?».
- Bruno: «¿Qué tratamiento sigue Bruno Demo?» y «¿Qué medicamento recibe?».
- Carla: «¿Qué medicamento recibe Carla Demo?» y «¿A qué es alérgica?».
- Datos ausentes: «¿Cuál es la dosis de omeprazol de Ana?», «¿Cuál fue la última cirugía de Ana?» y «¿A qué medicamento es alérgica Carla?».

Las dosis no están registradas. Tampoco hay una cirugía de Ana ni una alergia farmacológica documentada de Carla: su alergia al polen no demuestra una alergia a medicamentos. Estos huecos son intencionales para comprobar que la respuesta no invente información.

Los medicamentos son antecedentes de estos ejemplos, no indicaciones que el chat deba recetar. Las molestias escritas en consultas posteriores no se atribuyen automáticamente a una enfermedad o a un efecto adverso. Las preguntas de prueba que envíes con **Comparar y guardar** también quedarán en el diario.

El catálogo reproducible está en [casos_clinicos.json](casos_clinicos.json); los informes activos están en `historias/`. Actualizar el catálogo conserva las consultas anteriores como historial de su ejecución, sin reescribir las respuestas que recibieron con el corpus anterior.

Para actualizar una instalación que aún usa Alfa/Beta/Gamma, desde `codigo/` con las APIs encendidas:

```powershell
python -X utf8 scripts/actualizar_casos_demo.py --apply --output ejecuciones/casos-demo-1.json
```

El script verifica identidad y contenido antes de cambiar los tres registros demo; conserva el resto del informe y usa Java para mantener el respaldo SQL. Si detecta una edición distinta del original o del nuevo caso, se detiene para no sobreescribirla. Usa otro nombre de salida al repetirlo: cada ejecución conserva su propio respaldo y resultado.

Fuentes consultadas el 07/11/2026 para dar coherencia a los ejemplos, sin copiar historias de personas reales:

- Reflujo y hábitos: [NIDDK](https://www.niddk.nih.gov/health-information/digestive-diseases/acid-reflux-ger-gerd-adults).
- Omeprazol para el reflujo: [NHS](https://www.nhs.uk/medicines/omeprazole/).
- Diabetes y su manejo: [NIDDK](https://www.niddk.nih.gov/health-information/diabetes/overview/what-is-diabetes/type-2-diabetes) y [NHS](https://www.nhs.uk/conditions/type-2-diabetes/treatment/).
- Rinitis alérgica y medidas de tratamiento: [NHS](https://www.nhs.uk/conditions/allergic-rhinitis/).
- Cetirizina: [NHS](https://www.nhs.uk/medicines/cetirizine/about-cetirizine/).
