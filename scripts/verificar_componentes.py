"""Comprueba los accesos locales y guarda también los fallos; no arranca servicios."""

import argparse
import json
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
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
            # Solo el servidor local de esta práctica usa certificado autofirmado.
            context = ssl._create_unverified_context() if url == "https://localhost:8443/" else None
            with urlopen(url, timeout=15, context=context) as response:
                check["status"] = response.status
                assert response.status == 200, f"HTTP {response.status}"
                assert response.read(), "Respuesta vacía"
        except Exception as error:
            check["error"] = str(error)
        checks.append(check)
    output = Path(args.output)
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
