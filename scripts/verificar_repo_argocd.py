"""Comprueba que Argo CD conecta a Git y descubre el chart de una revisión exacta."""

import argparse
import base64
import json
import ssl
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", default="evidencias/s09/041-repositorio.json")
    args = parser.parse_args()
    kubectl = Path(__file__).resolve().parents[1] / ".local/bin/kubectl.exe"
    secret = json.loads(subprocess.check_output([
        str(kubectl), "--context=genai", "-n", "argocd", "get", "secret",
        "argocd-initial-admin-secret", "-o", "json",
    ], encoding="utf-8"))
    password = base64.b64decode(secret["data"]["password"]).decode()
    # Solo este cliente local acepta el certificado autofirmado de Argo CD.
    context = ssl._create_unverified_context()
    token = None

    def request(path, body=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body).encode() if body is not None else None
        with urlopen(Request("https://localhost:8443" + path, data=data, headers=headers),
                     context=context, timeout=60) as response:
            return json.load(response)

    token = request("/api/v1/session", {"username": "admin", "password": password})["token"]
    repo_url = "https://github.com/saico09/GenAIRUIFormacion2026.git"
    endpoint = "/api/v1/repositories/" + quote(repo_url, safe="")
    repository = request(endpoint + "?forceRefresh=true")
    assert repository["connectionState"]["status"] == "Successful", repository["connectionState"]
    # El descubrimiento comprueba permisos del proyecto; omitirlo busca un proyecto vacio.
    apps = request(endpoint + "/apps?" + urlencode({
        "revision": args.commit, "appProject": "default", "appName": "fastapi",
    }))
    assert any(item["path"] == "deploy/helm/fastapi" and item["type"] == "Helm"
               for item in apps.get("items", [])), apps
    evidence = {
        "checked_at": datetime.now(timezone.utc).isoformat(), "repo": repo_url,
        "commit": args.commit, "connection": repository["connectionState"],
        "applications_found": apps["items"], "project": "default", "ui": "https://localhost:8443",
    }
    Path(args.output).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("OK Argo CD conecta a Git y lee deploy/helm/fastapi en " + args.commit)


if __name__ == "__main__":
    main()
