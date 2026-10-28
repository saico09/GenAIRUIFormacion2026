# HDU-041 · Instalación local de Argo CD

Comprobado el 28/10/2026 en el contexto `genai`, namespace `argocd`. Argo CD ejecuta **v3.5.6**: seis Deployments `Available`, el controlador StatefulSet `1/1` y los siete pods `Ready`, sin reinicios en la comprobación. [Instalación](041-instalacion.json), [salida de comandos](041-instalacion.txt), [componentes](041-componentes.txt).

Para repetir desde `codigo/`:

```powershell
.\scripts\instalar_argocd.ps1
.\scripts\abrir_argocd.ps1
```

El instalador descarga el [manifiesto oficial fijado a v3.5.6](https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.6/manifests/install.yaml), verifica SHA-256 `846c644bc81ce5557dd9048757a9c7353378f25c5eb811c77d32a9e907823599` y lo aplica con `--server-side`. No fue necesario usar `--force-conflicts`. Todos sus comandos usan `--context=genai`; no cambia el contexto activo de kubectl.

La interfaz queda en **https://localhost:8443**. `abrir_argocd.ps1` inicia este comando con `Start-Process -WindowStyle Hidden`:

```powershell
.\.local\bin\kubectl.exe --context=genai -n argocd port-forward svc/argocd-server 8443:443 --address=127.0.0.1
```

El proceso conserva logs y PID en `.local/argocd-port-forward.*`, ignorados por Git. Una segunda ejecución del helper reconoció el port-forward existente y lo reutilizó. Si el puerto pertenece a otro proceso, el helper informa el conflicto sin detenerlo.

Se comprobaron HTTP 200 de la página y `/api/version` con `v3.5.6`. El certificado local es autofirmado; la comprobación de curl usó `--insecure` solamente contra `127.0.0.1:8443`. [Acceso comprobado](041-acceso.json).

Esta instalación no leyó la clave inicial, no la guardó en evidencias y no creó Applications. La conexión del repositorio y comprobación visual se registran aparte, como parte del cierre de la HDU-041. La explicación de Marco y revisión de Rui siguen pendientes.
