"""Auditoría actual sin LLM: un temporal propio, APIs reales y SQL de sólo lectura.

Desde codigo: python -B scripts/verificar_backend_cruzado.py inventory
Después: sustituir inventory por crud. No reinicia ni reconstruye servicios.
La limpieza usa las APIs; los respaldos y logs del temporal se conservan por diseño.
"""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
OUT = REPO / '.local' / 'verificaciones' / datetime.now(timezone.utc).strftime('backend-%Y%m%dT%H%M%SZ')
PRIVATE = OUT / 'privado'
PYTHON = 'genairuiformacion2026-python-api-1'
JAVA = 'genairuiformacion2026-java-api-1'
BASES = {'python': 'http://localhost:8000', 'java': 'http://localhost:8080'}
TABLES = ('patients', 'patient_diseases', 'medical_consultations', 'transaction_logs')
HTTP = []
REPORT = {'started_at': datetime.now(timezone.utc).isoformat(), 'checks': [], 'requests': HTTP}
CORRELATION = str(uuid4())


def sha(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return hashlib.sha256(value).hexdigest()


def run(args, input=None):
    result = subprocess.run(args, cwd=REPO, input=input, text=True, encoding='utf-8',
                            errors='replace', capture_output=True, timeout=40)
    if result.returncode:
        raise RuntimeError(f'{args[0]} devolvió {result.returncode}; salida privada omitida')
    return result.stdout


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, default=str)
        stream.write('\n')


def check(name, condition, details=None):
    REPORT['checks'].append({'name': name, 'passed': bool(condition), 'details': details})
    if not condition:
        raise AssertionError(name)


def containers():
    ids = run(['docker', 'ps', '-aq']).split()
    rows = json.loads(run(['docker', 'inspect', *ids]))
    return {r['Name'].lstrip('/'): {'id': r['Id'], 'state': r['State']['Status'],
            'image': r['Image'], 'restart_count': r['RestartCount'],
            'project': (r['Config'].get('Labels') or {}).get('com.docker.compose.project'),
            'service': (r['Config'].get('Labels') or {}).get('com.docker.compose.service')}
            for r in rows}


def sql_snapshot(patient_id=None):
    script = r'''
import hashlib,json
from pathlib import Path
from sqlalchemy import text
from app.db import engine
from app.history_documents import parse_history
tables=('patients','patient_diseases','medical_consultations','transaction_logs')
result={}
with engine.connect() as c:
 c.exec_driver_sql('SET TRANSACTION READ ONLY')
 assert c.exec_driver_sql('SHOW transaction_read_only').scalar_one()=='on'
 result['transaction_read_only']=True
 result['tables']=[dict(r) for r in c.execute(text("SELECT table_schema,table_name FROM information_schema.tables WHERE table_schema IN ('public','java') ORDER BY table_schema,table_name")).mappings()]
 result['columns']={table:[dict(r) for r in c.execute(text("SELECT column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name=:table ORDER BY ordinal_position"),{'table':table}).mappings()] for table in tables}
 result['row_hashes']={table:{r['id']:r['md5'] for r in c.execute(text('SELECT id::text AS id,md5(to_jsonb(t)::text) AS md5 FROM public.'+table+' t ORDER BY id')).mappings()} for table in tables}
 result['patients']=[dict(r) for r in c.execute(text('SELECT id,name,birth_date,email FROM public.patients ORDER BY id')).mappings()]
 result['diseases']=[dict(r) for r in c.execute(text('SELECT id::text,patient_id,disease,treatment,medication FROM public.patient_diseases ORDER BY patient_id,id')).mappings()]
 result['md']={}
 result['alignment']=[]
 for p in result['patients']:
  paths=list(Path('/datos/historias').glob(f"paciente-{p['id']}-*.md"))
  item={'patient_id':p['id'],'files':len(paths)}
  if len(paths)==1:
   path=paths[0]; raw=path.read_bytes(); history=parse_history(raw.decode('utf-8'),path.name)
   digest=hashlib.sha256(raw).hexdigest()
   result['md'][path.name]=digest
   rows=[{k:d[k] for k in ('id','disease','treatment','medication')} for d in result['diseases'] if d['patient_id']==p['id']]
   latest=c.execute(text('SELECT id::text,kind,filename,markdown_content,revision FROM public.medical_consultations WHERE patient_id=:pid ORDER BY storage_order DESC LIMIT 1'),{'pid':p['id']}).mappings().first()
   item.update({'filename':path.name,'sha256':digest,'record_count':len(rows),'records_match_md':rows==sorted(history['entries'],key=lambda r:r['id']),
    'latest_snapshot_id':latest['id'] if latest else None,'latest_snapshot_kind':latest['kind'] if latest else None,
    'latest_snapshot_matches':bool(latest and latest['filename']==path.name and latest['markdown_content'].encode('utf-8')==raw and latest['revision']==digest)})
  result['alignment'].append(item)
 result['log_uniqueness']=dict(c.execute(text('SELECT count(*) AS rows,count(DISTINCT id) AS unique_ids FROM public.transaction_logs')).mappings().one())
 result['snapshot_kinds']=[dict(r) for r in c.execute(text('SELECT kind,count(*) AS rows FROM public.medical_consultations GROUP BY kind ORDER BY kind')).mappings()]
 if patient_id is not None:
  result['temporary_snapshots']=[dict(r) for r in c.execute(text('SELECT id::text,execution_id::text,patient_id,kind,filename,revision,storage_order FROM public.medical_consultations WHERE patient_id=:pid ORDER BY storage_order'),{'pid':patient_id}).mappings()]
  result['temporary_logs']=[dict(r) for r in c.execute(text('SELECT id::text,patient_id,service,operation,method,path,http_status,request_body,response_body FROM public.transaction_logs WHERE patient_id=:pid ORDER BY created_at,id'),{'pid':patient_id}).mappings()]
 c.rollback()
print(json.dumps(result,default=str))
'''
    return json.loads(run(['docker', 'exec', '-i', PYTHON, 'python', '-B', '-'],
                          input=f'patient_id={patient_id!r}\n'+script))


def summary(snapshot):
    return {**{k:v for k,v in snapshot.items() if k not in ('row_hashes','temporary_logs')},
            'row_sets': {table: {'rows':len(rows),'hash_sha256':sha(rows)} for table,rows in snapshot['row_hashes'].items()}}


def http(service, method, path, body=None, expected=200):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    headers={'X-Execution-ID':CORRELATION}
    if data is not None:
        headers['Content-Type']='application/json'
    try:
        response=urlopen(Request(BASES[service]+path,data=data,method=method,headers=headers),timeout=20)
    except HTTPError as error:
        response=error
    with response:
        raw=response.read()
        try: payload=json.loads(raw)
        except ValueError: payload=raw.decode('utf-8',errors='replace')
        HTTP.append({'service':service,'method':method,'path':path,'status':response.status,
                     'request':body,'response':payload})
        if response.status != expected:
            raise AssertionError(f'{service} {method} {path}: {response.status}, esperado {expected}')
        return payload


def alignment(snapshot, pid, records):
    selected=[row for row in snapshot['alignment'] if row['patient_id']==pid]
    return len(selected)==1 and selected[0]['files']==1 and selected[0]['records_match_md'] and selected[0]['latest_snapshot_matches'] and selected[0]['record_count']==records


def inventory():
    current=sql_snapshot()
    source=REPO/'python-api'
    files=list((source/'app').rglob('*'))+list(source.glob('*.py'))+[source/'requirements.txt']
    local={p.relative_to(source).as_posix():sha(p.read_bytes().replace(b'\r\n',b'\n')) for p in files if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    script="""import json,hashlib
from pathlib import Path
root=Path('/code')
files=list((root/'app').rglob('*'))+list(root.glob('*.py'))+[root/'requirements.txt']
print(json.dumps({p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes().replace(b'\\r\\n',b'\\n')).hexdigest() for p in files if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}))
"""
    served=json.loads(run(['docker','exec','-i',PYTHON,'python','-B','-'],input=script))
    java_sources={str(p.relative_to(REPO/'java-api')):sha(p.read_bytes().replace(b'\r\n',b'\n')) for p in (REPO/'java-api'/'src').rglob('*') if p.is_file()}
    result={'time':datetime.now(timezone.utc).isoformat(),'git_head':run(['git','rev-parse','HEAD']).strip(),
            'git_status':run(['git','status','--short']).splitlines(), 'containers':containers(),
            'python_source':{'files':len(local),'matches_live':local==served,'local_hash':sha(local),'served_hash':sha(served)},
            'java_source':{'files':len(java_sources),'hash':sha(java_sources),'last_source_commit':run(['git','log','-1','--format=%H','--','java-api']).strip(),
              'live_jar_sha256':run(['docker','exec',JAVA,'sha256sum','/app/app.jar']).split()[0],
              'limit':'El JAR se identifica por hash; no se recompila para deducir igualdad binaria con las fuentes.'},
            'database':summary(current)}
    for service in BASES:
        result[service+'_health']=http(service,'GET','/health')
    spec=http('python','GET','/openapi.json')
    result['live_python_routes']={path:sorted(methods) for path,methods in spec['paths'].items() if '/patients' in path}
    result['checks']={'same_python_source':local==served,'all_existing_md_sql_aligned':all(alignment(current,p['id'],sum(d['patient_id']==p['id'] for d in current['diseases'])) for p in current['patients']),
                      'log_single_uuid':[r['column_name'] for r in current['columns']['transaction_logs'] if r['data_type']=='uuid']==['id']}
    write_new(OUT/'backend-inventario.json',result)
    print(json.dumps({'checks':result['checks'],'patients':len(current['patients']),'rows':{t:len(v) for t,v in current['row_hashes'].items()},'python_routes':len(result['live_python_routes'])},ensure_ascii=False))


def crud():
    before=sql_snapshot()
    before_containers=containers()
    write_new(PRIVATE/'backend-antes.json',before)
    REPORT['before']=summary(before)
    REPORT['correlation_header']=CORRELATION
    REPORT['scope']='Un paciente temporal, sin /chat, propuestas, sincronización del índice, inferencias ni reinicios.'
    pid=None
    name='QA Backend Revision 20261111 '+uuid4().hex[:8]
    marker_email='qa-'+uuid4().hex[:8]+'@example.com'
    payload={'name':name,'birth_date':'1995-06-15','email':marker_email}
    error=None
    try:
        lists={s:http(s,'GET','/patients') for s in BASES}
        check('Ambas APIs muestran los pacientes reales iniciales',lists['python']==lists['java']==before['patients'])
        created=http('python','POST','/patients',payload,201)
        pid=created['id']
        write_new(PRIVATE/'backend-temporal.json',{'patient_id':pid,'name':name,'email':marker_email,'created_at':datetime.now(timezone.utc).isoformat()})
        REPORT['temporary_patient_id']=pid
        print(json.dumps({'temporary_patient_id':pid,'name':name}),flush=True)
        check('Alta Python visible por Java',http('java','GET',f'/patients/{pid}')==created)
        auto=sql_snapshot(pid)
        check('Alta genera Markdown y respaldo SQL automáticamente',alignment(auto,pid,0),[a for a in auto['alignment'] if a['patient_id']==pid])
        original_filename=next(a['filename'] for a in auto['alignment'] if a['patient_id']==pid)
        payload['name']=name+' Renombrado Java'
        changed=http('java','PUT',f'/patients/{pid}',payload)
        check('Actualizar paciente Java se refleja en Python',http('python','GET',f'/patients/{pid}')==changed)
        renamed=sql_snapshot(pid)
        check('Renombrar conserva asociación y único MD',alignment(renamed,pid,0) and original_filename not in renamed['md'])
        a={'disease':'Rinitis alérgica de prueba','treatment':'Evitar el desencadenante descrito en el caso sintético','medication':'Cetirizina de prueba, sin pauta'}
        first=http('python','POST',f'/patients/{pid}/diseases',a,201)
        UUID(first['id'])
        check('Enfermedad Python visible por Java',http('java','GET',f"/patients/{pid}/diseases/{first['id']}")==first)
        a['treatment']='Plan actualizado mediante Java para el caso sintético'
        updated=http('java','PUT',f"/patients/{pid}/diseases/{first['id']}",a)
        check('Tratamiento Java visible por Python',http('python','GET',f"/patients/{pid}/diseases/{first['id']}")==updated)
        check('UUID y tres campos coinciden SQL/MD tras editar Java',alignment(sql_snapshot(pid),pid,1))
        b={'disease':'Reflujo de prueba','treatment':'Seguimiento ficticio','medication':'Omeprazol de prueba, sin pauta'}
        second=http('java','POST',f'/patients/{pid}/diseases',b,201)
        b['medication']='Medicamento de prueba editado mediante Python'
        edited=http('python','PUT',f"/patients/{pid}/diseases/{second['id']}",b)
        check('Alta Java y medicamento editado Python se ven en ambas APIs',http('java','GET',f"/patients/{pid}/diseases/{second['id']}")==edited)
        check('Listado enfermedades cruzado idéntico',http('python','GET',f'/patients/{pid}/diseases')==http('java','GET',f'/patients/{pid}/diseases'))
        check('Dos registros alineados con respaldo SQL',alignment(sql_snapshot(pid),pid,2))
        history=http('java','GET',f'/patients/{pid}/history')
        downloaded=http('java','GET',f'/patients/{pid}/history.md')
        check('Descarga Markdown coincide con historia y SQL',downloaded==history['markdown'] and sha(downloaded.encode())==history['revision'])
        replacement=history['markdown'].replace('Seguimiento ficticio','Seguimiento ficticio editado desde Markdown')
        changed_history=http('java','PUT',f'/patients/{pid}/history',{'revision':history['revision'],'markdown':replacement,'confirmed':True})
        check('Edición confirmada MD actualiza tabla y respaldo',changed_history['markdown']==replacement and alignment(sql_snapshot(pid),pid,2) and http('python','GET',f"/patients/{pid}/diseases/{second['id']}")['treatment']=='Seguimiento ficticio editado desde Markdown')
        http('java','DELETE',f"/patients/{pid}/diseases/{first['id']}",expected=204)
        http('python','GET',f"/patients/{pid}/diseases/{first['id']}",expected=404)
        http('python','DELETE',f"/patients/{pid}/diseases/{second['id']}",expected=204)
        http('java','GET',f"/patients/{pid}/diseases/{second['id']}",expected=404)
        check('Borrar enfermedades por cada API actualiza SQL/MD',alignment(sql_snapshot(pid),pid,0))
        payload['name']=name+' Renombrado Python'
        updated_patient=http('python','PUT',f'/patients/{pid}',payload)
        check('Actualización final Python visible en Java',http('java','GET',f'/patients/{pid}')==updated_patient and alignment(sql_snapshot(pid),pid,0))
    except Exception as caught:
        error=f'{type(caught).__name__}: {caught}'
        REPORT['error']=error
    finally:
        if pid is not None:
            try:
                owned=http('java','GET',f'/patients/{pid}')
                if not owned['name'].startswith(name) or owned['email']!=marker_email:
                    raise AssertionError('La identidad del temporal cambió: no se borra')
                http('java','DELETE',f'/patients/{pid}',expected=204)
                http('python','GET',f'/patients/{pid}',expected=404)
                http('java','GET',f'/patients/{pid}',expected=404)
                REPORT['cleanup']={'patient_id':pid,'deleted':True,'historical_rows_retained':True}
            except Exception as caught:
                REPORT['cleanup']={'patient_id':pid,'deleted':False,'error':f'{type(caught).__name__}: {caught}'}
                error=error or REPORT['cleanup']['error']
        try:
            after=sql_snapshot(pid)
            write_new(PRIVATE/'backend-despues.json',after)
            REPORT['after']=summary(after)
            preserved={table:all(after['row_hashes'][table].get(key)==value for key,value in hashes.items()) for table,hashes in before['row_hashes'].items()}
            check('Todas las filas previas se conservan sin cambios',all(preserved.values()),preserved)
            check('Pacientes y Markdown finales idénticos al baseline',before['patients']==after['patients'] and before['md']==after['md'])
            check('Ningún contenedor reiniciado o recreado',before_containers==containers())
            columns=after['columns']['transaction_logs']
            check('Auditoría tiene un UUID y patient_id', [c['column_name'] for c in columns if c['data_type']=='uuid']==['id'] and any(c['column_name']=='patient_id' and c['data_type']=='integer' for c in columns))
            logs=after.get('temporary_logs',[])
            expected=Counter((r['service'],r['method'],r['path'],r['status']) for r in HTTP if f'/patients/{pid}' in r['path'] or (r['method']=='POST' and r['path']=='/patients'))
            actual=Counter((r['service'],r['method'],r['path'],r['http_status']) for r in logs)
            check('Una fila de log por operación del temporal, UUID distintos',expected==actual and len({r['id'] for r in logs})==len(logs) and all(r['patient_id']==pid for r in logs),{'expected_operations':sum(expected.values()),'rows':len(logs),'distinct_uuids':len({r['id'] for r in logs})})
            REPORT['temporary_logs']=logs
            check('Los respaldos del temporal se conservan al borrarlo',bool(after.get('temporary_snapshots')) and after['temporary_snapshots'][-1]['kind']=='deleted')
        except Exception as caught:
            error=error or f'{type(caught).__name__}: {caught}'
            REPORT['final_check_error']=f'{type(caught).__name__}: {caught}'
        REPORT['status']='PASS' if error is None else 'FAIL'
        REPORT['finished_at']=datetime.now(timezone.utc).isoformat()
        REPORT['limits']='No se invoca chat ni LLM, no se prueba navegación UI, concurrencia, fallo de commit ni GitOps. Java se valida por contratos reales; el hash del JAR no certifica compilación reproducible.'
        write_new(OUT/'backend-crud-cruzado.json',REPORT)
        print(json.dumps({'status':REPORT['status'],'checks':len(REPORT['checks']),'http_requests':len(HTTP),'temporary_patient_id':pid,'cleanup':REPORT.get('cleanup'),'error':error},ensure_ascii=False))
    if error:
        raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('inventory','crud'),nargs='?',default='inventory')
    parser.add_argument('--output',type=Path,default=OUT)
    args=parser.parse_args()
    OUT=args.output.resolve()
    PRIVATE=OUT/'privado'
    {'inventory':inventory,'crud':crud}[args.phase]()
