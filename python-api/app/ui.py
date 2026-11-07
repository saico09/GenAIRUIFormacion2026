"""Interfaz local y configuración pública de sus dos APIs; no contiene credenciales."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def install_ui(app: FastAPI) -> None:
    static_dir = Path(__file__).parent / "static"
    java_port = int(os.getenv("JAVA_API_PUBLIC_PORT", "8080"))
    if not 1 <= java_port <= 65535:
        raise ValueError("JAVA_API_PUBLIC_PORT debe ser un puerto entre 1 y 65535")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/ui-config", include_in_schema=False)
    def ui_config():
        # Las copias S4/S5 no ofrecen métricas; el explorador respeta ese alcance.
        return {"java_api_port": java_port,
                "metrics_enabled": any(getattr(route, "path", None) == "/metrics" for route in app.routes)}
