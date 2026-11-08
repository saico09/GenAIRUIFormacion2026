# Casos reales en nombre, ficticios en identidad

Por petición de Marco, los ejemplos Alfa/Beta/Gamma se sustituyen por casos inventados de reflujo gastroesofágico, diabetes tipo 2 y rinitis alérgica estacional. Tratamientos, medicamentos y fuentes oficiales están en [CASOS.md](../../datos/CASOS.md); el catálogo reproducible está en [casos_clinicos.json](../../datos/casos_clinicos.json).

Los mismos tres UUID siguen asociando enfermedad, tratamiento y medicamento. El migrador verificó las tres identidades y el contenido original antes de escribir mediante Java. Conservó las consultas anteriores de Ana, los demás registros y las revisiones SQL. La primera ejecución reemplazó tres registros; la segunda no escribió ninguno. [Resultado](migracion-principal.json).

Un primer preflight detectó saltos CRLF en dos informes y se detuvo sin escribir. Se corrigió la normalización al formato LF que genera Java; el contenido del diario y los campos ajenos se conservan. Los respaldos completos de los datos anteriores permanecen fuera de Git. Las semillas publicadas no incluyen el diario local de Ana.

El prompt usa nombres reales sin atribuir propiedades clínicas a antecedentes inexistentes. La validación de citas diferencia una alergia ambiental de una alergia farmacológica y rechaza una dosis no documentada. Pasaron los [10 contratos nuevos](contratos-corpus.txt) y los [25 contratos anteriores](contratos-historia.txt) contra el Python reconstruido.

Pasaron **14/14 preguntas con Ollama y Qdrant reales**. Cada respuesta conocida tiene citas del paciente correcto; las preguntas sin antecedente y la pregunta por otro paciente se abstienen. Los tres informes completos y el índice conservaron sus hashes durante el ensayo. [Respuestas, fuentes y comprobaciones](rag-real.json).

Para repetir el ensayo de recuperación y modelo reales, sin añadir consultas al diario:

```powershell
python -X utf8 scripts/verificar_corpus_realista.py --output ejecuciones/corpus-rag-1.json
```

Comprueba los tres campos de cada paciente, el polen, dosis/cirugía/alergias farmacológicas ausentes y una pregunta sobre otro paciente. Usa los mismos parámetros de Qwen que la app, pero no llama a `/chat`: no acredita por sí solo la interfaz ni el guardado de una conversación. Sus GET de Java sí generan auditoría. Los hashes verifican que no cambie el Markdown ni Qdrant. No es una medición general de precisión clínica.

Esta revisión modifica el corpus de la capacitación; no convierte sus casos en datos reales, no cambia las 48 HDU/80 horas ni acredita horas o revisión humana. Los ensayos y comentarios anteriores que mencionan Alfa/Beta/Gamma conservan su valor histórico.
