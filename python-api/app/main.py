from fastapi import FastAPI

app = FastAPI(title="python-api")


@app.get("/health")
def health():
    # FastAPI convierte el dict a JSON y responde 200 por defecto
    return {"status": "ok"}
