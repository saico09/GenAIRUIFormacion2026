"""Ensayo de las tres consultas originales de Ana: modelo real, MD, SQL y reintento.

Registra deliberadamente esas tres consultas en Ana. Los UUID estables permiten
repetir el ensayo sin duplicarlas. No escribe diagnósticos ni recetas confirmados.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidencias/consultas-automaticas-2026-11-07/ana-consultas.json'
CHAT_MODEL = os.getenv('CHAT_MODEL', 'qwen3.5:4b-q4_K_M')
CASES = [
    ('c5a3b358-1e9d-468f-b29f-0bbe49cd4496', 'tiene indigestión aguda y le duele la cabeza'),
    ('aac69259-a232-4d86-be8a-58c50228f4fe', 'tiene dolor estomacal y diarrea'),
    ('5bd7851e-de0d-47b9-9fd6-9b2ac1529bf4', 'aprieta los dientes en la noche y tiene temblores en las manos'),
]


def http(port, path, payload=None, identifier=None):
    headers = {'Content-Type': 'application/json'}
    if identifier:
        headers['X-Execution-ID'] = identifier
    req = Request(f'http://localhost:{port}{path}', data=json.dumps(payload, ensure_ascii=False).encode() if payload else None, headers=headers)
    try:
        response = urlopen(req, timeout=420)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response), response.headers.get('X-Execution-ID')


def main():
    before = http(8080, '/patients/1/history')[1]
    report = {'scope': 'APIs/SQL/LLM reales en Compose principal; reejecución de las tres consultas del usuario.', 'cases': []}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for identifier, question in CASES:
        start = perf_counter()
        code, result, header = http(8000, '/chat', {'patient_id': 1, 'question': question}, identifier)
        row = {'id': identifier, 'question': question, 'http': code, 'result': result, 'seconds': round(perf_counter()-start, 2)}
        history = http(8080, '/patients/1/history')[1]
        saved = [c for c in history['consultations'] if c['id'] == identifier]
        row['checks'] = {'http_200': code == 200, 'execution_header': header == identifier,
                         # Reintenta UUID históricos: sus respuestas originales no se reescriben.
                         'useful_orientation': any(label in result.get('rag_answer', '') for label in
                                                   ('Diagnóstico orientativo (sin confirmar)', 'Orientación general')),
                         'saved_once': len(saved) == 1, 'md_contains_input': question in history['markdown'],
                         'md_contains_answers': all(result.get(k, '!missing!') in history['markdown'].replace('\n> ', '\n') for k in ('direct_answer', 'rag_answer')),
                         'confirmed_entries_unchanged': history['entries'] == before['entries'],
                         'rag_synced': result.get('index_synced') is True,
                         'chosen_model': result.get('model') == next(
                             (c['model'] for c in before['consultations'] if c['id'] == identifier), CHAT_MODEL)}
        row['passed'] = all(row['checks'].values())
        report['cases'].append(row)
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({'id': identifier, 'passed': row['passed'], 'checks': row['checks']}, ensure_ascii=False), flush=True)
        if code != 200:
            raise RuntimeError(result)
    identifier, question = CASES[0]
    code, repeated, _ = http(8000, '/chat', {'patient_id': 1, 'question': question}, identifier)
    report['retry_cached'] = code == 200 and repeated['rag_answer'] == report['cases'][0]['result']['rag_answer']
    code, conflict, _ = http(8000, '/chat', {'patient_id': 1, 'question': 'Pregunta distinta'}, identifier)
    report['different_input_409'] = code == 409
    final = http(8080, '/patients/1/history')[1]
    report['all_three_unique'] = all(sum(c['id'] == i for c in final['consultations']) == 1 for i, _ in CASES)
    report['md_sha256'] = hashlib.sha256((ROOT/'datos/historias'/final['filename']).read_bytes()).hexdigest()
    report['revision_matches_file'] = report['md_sha256'] == final['revision']
    # Lee usando la configuración interna existente; no imprime credenciales.
    program = '''import json
from sqlalchemy import text
from app.db import engine
with engine.connect() as c:
 rows=c.execute(text("SELECT id::text, revision, markdown_content FROM public.medical_consultations WHERE patient_id=1 ORDER BY storage_order")).mappings().all()
 logs=c.execute(text("SELECT id::text,patient_id,service,operation,http_status,request_truncated,response_truncated FROM public.transaction_logs WHERE patient_id=1 ORDER BY created_at")).mappings().all()
 print(json.dumps({'consultations':[dict(x) for x in rows], 'logs':[dict(x) for x in logs]}))
'''
    sql = json.loads(subprocess.check_output(['docker','exec','genairuiformacion2026-python-api-1','python','-c',program], text=True, encoding='utf-8'))
    report['sql_consultations'] = [{k:v for k,v in row.items() if k != 'markdown_content'} for row in sql['consultations']]
    report['sql_matches_latest_md'] = sql['consultations'][-1]['markdown_content'] == final['markdown']
    report['patient_logs'] = sql['logs']
    report['both_services_for_patient'] = {'java','python'} <= {row['service'] for row in sql['logs']}
    report['passed'] = all(row['passed'] for row in report['cases']) and all(report[k] for k in
        ('retry_cached','different_input_409','all_three_unique','revision_matches_file','sql_matches_latest_md','both_services_for_patient'))
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    assert report['passed'], 'Revisar evidencia del ensayo'
    print('PASS tres consultas + reintento + SQL/MD/auditoría')


if __name__ == '__main__':
    main()
