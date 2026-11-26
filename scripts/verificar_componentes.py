"""Comprueba los accesos locales y guarda también los fallos; no arranca servicios."""

import argparse
import json
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

OUTPUT = Path(__file__).resolve().parents[1] / ".local" / "verificaciones" / f"{Path(__file__).stem}-{datetime.now():%Y%m%dT%H%M%S}.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--argo-ca", type=Path, help="Certificado CA de Argo CD para verificar su HTTPS local")
    args = parser.parse_args()
    endpoints = (
        ("FastAPI", "http://localhost:8000/health"),
        ("Spring Boot", "http://localhost:8080/health"),
        ("Chatbot", "http://localhost:8000/"),
        ("Grafana", "http://localhost:3000/api/health"),
        ("Phoenix", "http://localhost:6006/"),
        ("Argo CD", "https://localhost:8443/"),
        ("Loki", "http://localhost:3100/ready"),
        ("FastAPI Minikube", "http://localhost:8002/patients/1"),
    )
    checks = []
    for component, url in endpoints:
        check = {"component": component, "url": url, "status": None}
        try:
            # Con CA propia se valida tanto la cadena como el nombre del servidor.
            context = ssl.create_default_context(cafile=args.argo_ca) if url.startswith("https://") else None
            with urlopen(url, timeout=15, context=context) as response:
                check["status"] = response.status
                if response.status != 200:
                    check["error"] = f"HTTP {response.status}"
                elif not response.read():
                    check["error"] = "Respuesta vacía"
        except Exception as error:
            check["error"] = str(error)
        checks.append(check)
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "checked_at": datetime.now(timezone.utc).isoformat(), "checks": checks,
        "note": "Comprueba acceso al entorno existente; no acredita un arranque desde detenido.",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failures = [check["component"] for check in checks if "error" in check]
    if failures:
        raise SystemExit("Fallaron: " + ", ".join(failures))
    print(f"OK {len(checks)} componentes HTTP 200; {output}")


if __name__ == "__main__":
    main()
