"""Cotejo de la consulta creada por el navegador; el reintento no debe generar otra."""
import hashlib
import json
from pathlib import Path
import subprocess
from time import perf_counter
from urllib.request import Request, urlopen

PATIENT = 58
EXECUTION = "f48576ae-00e8-4d80-91eb-24a214d83f06"
QUESTION = "dolor de estómago"
OUT = Path(__file__).resolve().parent


def http(url, body=None, headers=None):
    request = Request(url, data=None if body is None else json.dumps(body).encode(),
                      headers={"Content-Type": "application/json", **(headers or {})})
    with urlopen(request, timeout=30) as response:
        assert response.status == 200
        return json.load(response)


history_url = f"http://localhost:8080/patients/{PATIENT}/history"
before = http(history_url)
assert len(before["entries"]) == len(before["consultations"]) == 1
assert before["consultations"][0]["id"] == EXECUTION
started = perf_counter()
replayed = http("http://localhost:8000/chat", {"patient_id": PATIENT, "question": QUESTION},
                {"X-Execution-ID": EXECUTION})
elapsed = round(perf_counter() - started, 3)
after = http(history_url)
assert before == after
assert replayed["consultation"]["id"] == EXECUTION and replayed["index_synced"]
assert replayed["model"] == "qwen3.5:4b-q4_K_M"
assert all(replayed[field] == before["consultations"][0][field] for field in ("direct_answer", "rag_answer"))
assert all("Podría ser" in replayed[field] and "?" not in replayed[field] for field in ("direct_answer", "rag_answer"))
assert hashlib.sha256(before["markdown"].encode()).hexdigest() == before["revision"]
script = '''
import json
from sqlalchemy import text
from app.db import engine
with engine.connect() as connection:
    connection.execute(text("SET TRANSACTION READ ONLY"))
    result = connection.execute(text("""SELECT id::text, patient_id, revision,
        encode(sha256(convert_to(markdown_content,'UTF8')),'hex') AS md_hash
        FROM public.medical_consultations WHERE patient_id=58 ORDER BY storage_order DESC LIMIT 1""")).mappings().one()
    count = connection.execute(text("SELECT count(*) FROM public.medical_consultations WHERE patient_id=58 AND kind='consultation'")).scalar_one()
    records = connection.execute(text("SELECT count(*) FROM public.patient_diseases WHERE patient_id=58")).scalar_one()
    print(json.dumps({**dict(result), 'consultation_count':count, 'confirmed_count':records}))
'''
result = subprocess.run(["docker", "exec", "-i", "genairuiformacion2026-python-api-1", "python", "-"],
                        input=script, text=True, encoding="utf-8", capture_output=True, timeout=30, check=True)
sql = json.loads(result.stdout)
assert sql["id"] == EXECUTION and sql["revision"] == sql["md_hash"] == before["revision"]
assert sql["consultation_count"] == sql["confirmed_count"] == 1
report = {"patient_id": PATIENT, "execution_id": EXECUTION, "http_initial_ms": 24458.164,
          "replay_seconds": elapsed, "same_history_after_replay": True,
          "model": replayed["model"], "sql": sql,
          "checks": ["Respuesta de ambas ramas no vacía con posibilidades", "Sin interrogatorio",
                     "UUID único de la consulta y reintento idéntico", "SQL y Markdown coinciden",
                     "La hipótesis no agrega un registro confirmado"], "status": "PASS"}
(OUT / "ui-guardado-sql.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
