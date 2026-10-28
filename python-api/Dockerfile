FROM python:3.15.2-slim AS dependencies

WORKDIR /build
COPY requirements.txt .
# zstandard todavía requiere compilarse para Python 3.15; el compilador no pasa al runtime.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt

FROM python:3.15.2-slim

WORKDIR /code

# Primero las dependencias: si no cambian, Docker reutiliza esta capa
COPY requirements.txt .
RUN --mount=type=bind,from=dependencies,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

COPY app ./app
COPY *.py ./

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
