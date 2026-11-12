# Revisión breve: «dolor de estómago agudo»

Lectura independiente de [Gemma](agudo-lectura.json) y [Qwen](agudo-qwen-lectura.json), sin nuevas inferencias ni cambios de código. El usuario sólo aportó esas palabras; no indicó localización precisa, inicio repentino, intensidad, comidas, alcohol, fiebre ni vómitos.

| Salida | Evaluación de esta respuesta |
|---|---|
| Gemma / RAG | Cumple el mínimo de orientación condicional: ofrece posibilidades, condiciona la relación con ERGE a síntomas adicionales y distingue el antecedente. No atribuye esos síntomas al episodio actual. Límite: alternativas amplias y repetición del historial. |
| Gemma / directa | Cumple fidelidad y condicionalidad: propone posibilidades y usa «si» para los datos adicionales, sin inventar antecedentes. Límite: no desarrolla por igual las tres alternativas; no demuestra que sean las más probables para este relato. |
| Qwen / RAG | Rechazada para esta muestra: utiliza tener ERGE como fundamento del dolor actual sin datos que vinculen ambos. El antecedente citado es real dentro del caso ficticio; el problema es la asociación causal sugerida. Las alternativas posteriores son numerosas y poco discriminadas. |
| Qwen / directa | Rechazada: exige urgencia inmediata basándose sólo en «agudo» y justifica la hipótesis con ubicación epigástrica/comidas grasas/alcohol no relatados. Escribir «posible» no convierte esas premisas en evidencia aportada. |

NHS distingue causas posibles mediante síntomas acompañantes y considera una alarma concreta el dolor de inicio repentino **y** severo. También señala otras alarmas, como vomitar sangre. El término aislado «agudo» no demuestra por sí solo esas condiciones; si se mencionan, deben presentarse condicionalmente. Esto tampoco permite afirmar que no hay riesgo. [NHS: stomach ache](https://www.nhs.uk/symptoms/stomach-ache/), consultado el 11/11/2026 de Santiago.

## Mínimo propuesto para los próximos cuatro casos

Evaluar **cada rama por separado**, leyendo la respuesta completa; `questions=[]`, HTTP 200 y una cita válida no bastan.

| Caso | Para aceptar esta salida concreta |
|---|---|
| `dolor de estómago agudo` | Ofrece posibilidades sin deducir inicio repentino, intensidad severa ni localización. Vincula cualquier alternativa a condiciones explícitas; no declara urgencia presente sólo por «agudo». Si aparece una alarma nueva como condición, queda claro que no fue relatada. |
| `dolor de estómago` | Orienta con dos o tres causas posibles pertinentes, sin elegir una como confirmada. Explica al menos qué dato adicional favorecería una alternativa y no trata los antecedentes como explicación suficiente del episodio actual. |
| `dolor de cabeza` | Reconoce ese síntoma y ofrece posibilidades pertinentes condicionadas. No reutiliza el reflujo ni los medicamentos del historial como causa demostrada; no inventa duración, intensidad, desencadenantes ni síntomas neurológicos. |
| `me siento mal` | Reconoce que el malestar es inespecífico y no prioriza una enfermedad. Explica el límite de forma útil y permite aportar dos o tres detalles concretos opcionales, sin exigirlos para continuar ni presentar una lista arbitraria de diagnósticos. |

En los cuatro: respuesta breve y cerrada, sin interrogatorio ni preguntas; los detalles adicionales son opcionales. No atribuye síntomas/negaciones no aportados, no prescribe ni confirma diagnósticos, y los antecedentes de RAG quedan separados y respaldados por citas del material recuperado. La directa no afirma conocer el historial. Una alarma expresamente relatada debe tener prioridad; sin ella, no se inventa ni se descarta riesgo.

Estos criterios aceptan o rechazan respuestas de una muestra pequeña. No acreditan exactitud clínica general ni superioridad estable de un modelo. La velocidad observada tampoco compensa una premisa inventada; las dos ejecuciones no constituyen un benchmark controlado.
