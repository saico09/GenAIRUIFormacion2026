# Primera carga Java · 07/11/2026

El clon incluye tres informes Markdown. Con la tabla Java vacía, los POST individuales reservaban sus IDs y respondían 409 para no sobrescribirlos. Esa protección se conserva. La carga explícita `python inicializar_java.py` valida pacientes, propietarios y UUID, y asocia los IDs 1–3 solo si la tabla sigue completamente vacía bajo bloqueo. No escribe informes.

Si existe cualquier fila, devuelve `conservados` sin tocar filas ni secuencia; tampoco intenta completar una demo parcial. La siguiente identidad es al menos 4 y conserva valores ya consumidos. Se usa `ALTER SEQUENCE ... RESTART` dentro de la misma transacción: PostgreSQL documenta que [RESTART es transaccional](https://www.postgresql.org/docs/18/sql-altersequence.html), mientras que `setval` no tiene esa propiedad. El bloqueo [SHARE ROW EXCLUSIVE](https://www.postgresql.org/docs/18/explicit-locking.html) serializa la carga frente a otras escrituras y permite lecturas.

Ensayo real: [resultado JSON](bootstrap-java.json) y [build Python](bootstrap-java.build.txt). Diez comprobaciones pasaron en PostgreSQL y Java nuevos, con copias de los informes, red y volumen propios. Incluyen tres rechazos sin cambios, rollback de filas y secuencia por un error SQL provocado, protección 409, dos inicializadores simultáneos, alta API con ID 4, repetición sin cambios y una secuencia adelantada que continúa en 21. Los hashes de los tres Markdown se conservaron. Se eliminaron únicamente los tres contenedores, volumen, red, etiqueta de imagen y archivos temporales de este ensayo; el filtro de recursos etiquetados quedó vacío. No se usaron volúmenes principales o semanales ni se llamó al LLM.

Para repetir desde `codigo/`, con Python 3 y Docker disponibles (construye una imagen Python temporal; requiere la imagen Java ya construida):

```powershell
python scripts/verificar_inicializacion_java.py --output evidencias/clinica-2026-11-07/bootstrap-java-repeticion.json
```

La prueba solo recrea sus propios datos efímeros. No demuestra adopción de informes de pacientes distintos ni migración de una tabla parcialmente cargada: el comando deliberadamente no hace esas operaciones.
