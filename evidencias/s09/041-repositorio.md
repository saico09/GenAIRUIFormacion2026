# HDU-041 · Acceso y repositorio · 28/10/2026

Argo CD 3.5.6 quedó instalado con siete pods Ready en namespace `argocd`, contexto `genai`. [Instalación y acceso local](041-infra.md), [estado](041-instalacion.json) y [componentes](041-componentes.txt).

Se abrió **https://localhost:8443**, se inició sesión y se comprobó **Settings → Repositories → Successful**. [Resultado UI](041-ui.json) y [captura inspeccionada](041-argocd.png). `scripts/abrir_argocd.ps1` inicia el port-forward oculto sobre 127.0.0.1 y lo reutilizó en una segunda ejecución; PID y logs quedan en `.local`, fuera de Git.

| Dato | Resultado comprobado |
|---|---|
| Repositorio | `https://github.com/saico09/GenAIRUIFormacion2026.git`, público |
| Rama publicada | main |
| Commit leído | `1bc6af1235a6d96952334e41685c3acd829b3fed` |
| Proyecto Argo CD | default |
| Conexión | Successful, mensaje vacío |
| Chart descubierto | deploy/helm/fastapi, tipo Helm |

[041-repositorio.json](041-repositorio.json) conserva la respuesta real. `deploy/argocd/repositorio.yaml` declara el repo público mediante el Secret de configuración de Argo CD, sin usuario, token ni contraseña Git. El descubrimiento del chart no crea una Application; esta HDU todavía no despliega FastAPI.

La primera consulta de descubrimiento devolvió 404 porque el verificador omitía el proyecto. Se corrigió `scripts/verificar_repo_argocd.py` para enviar `appProject=default` y `appName=fastapi`; la repetición encontró el chart en el commit exacto. [Registro del problema y su resolución](bloqueos.md). No hay un bloqueo de lectura Git pendiente.

Los comandos comprobados de instalación, acceso, clave inicial local, registro del repositorio y verificación están en [GUIA.md](../../GUIA.md#preparar-argo-cd). La clave y el token de sesión se usaron solo en memoria para las pruebas y no se guardaron en evidencias. La consulta de la clave incluida en la guía también se probó sin mostrar ni guardar su valor durante la comprobación documental.

La Application corresponde a HDU-042. Explicación de Marco y revisión de Rui siguen pendientes; esta evidencia no acredita horas ni una sesión realizada.
