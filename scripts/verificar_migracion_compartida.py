"""Coteja filas previas de un pg_dump local con el esquema unificado, sin publicar datos."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--backup',type=Path,required=True)
parser.add_argument('--container',default='genairuiformacion2026-postgres-1')
parser.add_argument('--output',type=Path,required=True)
args = parser.parse_args()
dump = args.backup.read_text(encoding='utf-8')
report = {'backup_sha256':hashlib.sha256(args.backup.read_bytes()).hexdigest(),'tables':[]}
mapping = {'public.patients':'public.patients','java.patients':'public.patients',
           'java.medical_consultations':'public.medical_consultations','public.transaction_logs':'public.transaction_logs'}
for previous,current in mapping.items():
    found = re.search(rf'^COPY {re.escape(previous)} \((.*?)\) FROM stdin;\n(.*?)\n\\\.$',dump,re.M|re.S)
    if not found:
        raise ValueError(f'Falta tabla original en respaldo: {previous}')
    columns = found[1].split(', ')
    retained = [c for c in columns if not (previous=='public.transaction_logs' and c in ('execution_id','request_id'))]
    indexes = [columns.index(c) for c in retained]
    before = {values[0]:tuple(values[i] for i in indexes) for line in found[2].splitlines() if (values:=line.split('\t'))}
    command = '\\copy (SELECT '+','.join(retained)+' FROM '+current+') TO STDOUT;'
    live = subprocess.check_output(['docker','exec','-i',args.container,'sh','-c',
        'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"','sh',command],text=True,encoding='utf-8')
    after = {values[0]:tuple(values) for line in live.splitlines() if (values:=line.split('\t'))}
    mismatches = [key for key,values in before.items() if after.get(key)!=values]
    row = {'from':previous,'to':current,'original_rows':len(before),'current_rows':len(after),
           'columns_compared':retained,'original_rows_preserved':not mismatches}
    report['tables'].append(row)
    assert not mismatches, f'Cambió una fila previa en {previous}'
report['passed'] = all(t['original_rows_preserved'] for t in report['tables'])
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
