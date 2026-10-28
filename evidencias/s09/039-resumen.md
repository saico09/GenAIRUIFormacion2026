# HDU-039 · Entorno e imagen preparados

Comprobado el **28/10/2026**. El 04/01/2027 es la fecha prevista del plan, no la fecha de estas pruebas.

| Paso | Resultado y evidencia |
|---|---|
| Arranque del README | Compose terminó correctamente; `esperar_apis.ps1` confirmó ambas APIs y Ollama respondió. [Salida](039-arranque.txt). |
| Paciente y health | Ana existente y ambos health correctos. [Resultado](039-apis.json). |
| Pregunta RAG | Pregunta exacta del dataset sobre la enfermedad de Ana, Alfa con fuente, cinco spans y siete logs correlacionados. [Resultado](039-chat.json). |
| Herramientas | Minikube 1.39.0, kubectl 1.36.6 y Helm 4.3.1; SHA-256 y versiones comprobados en `.local/bin`, sin modificar PATH. [Evidencia](039-herramientas.json). |
| Nodo | `genai` Ready, Kubernetes v1.36.6, runtime containerd. [Espera](039-ready.txt), [salida de nodos](039-nodos.txt) y [JSON](039-nodos.json). |
| Recursos | 2 CPU y 3221225472 bytes, equivalentes a 3072 MiB, comprobados en el contenedor Minikube. [Recursos solicitados y reales](039-recursos.json). |
| Imagen | Build correcto y carga con exit 0; la lista contiene `docker.io/library/genai-fastapi:s09`. [Build](039-image-build.txt), [carga](039-image-load.txt) y [lista](039-images.txt). |

La comprobación RAG usó request_id `hdu039-04beba5ec0f64c7ea8e2843f4060f22c` y [traza `54ac6d385450e80b8fc9e7f78d494671`](http://localhost:6006/redirects/traces/54ac6d385450e80b8fc9e7f78d494671).

Inicio probado:

```powershell
.\.local\bin\minikube.exe start --profile=genai --driver=docker --cpus=2 --memory=3072 --kubernetes-version=v1.36.6 --keep-context --wait=all --wait-timeout=6m
```

`--keep-context` conserva el contexto activo. Las comprobaciones usan explícitamente `kubectl --context=genai` y `minikube --profile=genai`. El instalador, espera Ready, build, carga y listado están paso a paso en [GUIA.md](../../GUIA.md#preparar-minikube); la [salida de inicio](039-inicio.txt) conserva la descarga y preparación del clúster.

[039-imagen.json](039-imagen.json) registra la imagen Linux amd64 de 86026424 bytes, id `sha256:62d67d465efc66fd6bb591cfe044a2b978be2b373099bf0d919b745cca39274d`, construida desde el código del commit `c2bcfafa5b25e71f08e44fbba730a9c225e7cfee`.

La RAM libre observada quedó registrada; se continuó según la autorización de Marco y las pruebas reales pasaron. Esta HDU deja nodo e imagen preparados, sin instalar todavía un Deployment del microservicio. No acredita revisión de Rui, comprensión personal ni horas realizadas.
