"""Inspección de lectura del HTML, módulos, CSS y validación HTTP de caché."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'python-api/app/static'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=ROOT/'.local/verificaciones/assets-http.json')
args=parser.parse_args()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def get(url, headers=None):
    try:
        response = urlopen(Request(url, headers=headers or {}), timeout=20)
    except HTTPError as error:
        response = error
    except (URLError, TimeoutError) as error:
        return {'url': url, 'error': str(error)}, b''
    data = response.read()
    result = {'url': url, 'status': response.status, 'bytes': len(data), 'sha256': sha(data),
              'headers': {k.lower(): v for k, v in response.headers.items()}}
    return result, data

files = [path.name for path in STATIC.iterdir() if path.is_file()]
rows = []
for host in ['localhost', '127.0.0.1']:
    for relative in ['/', '/ui-config', *('/static/' + name for name in sorted(files))]:
        row, data = get('http://' + host + ':8000' + relative)
        local = STATIC / ('index.html' if relative == '/' else relative.rsplit('/', 1)[-1])
        if local.exists():
            row['local_sha256'] = sha(local.read_bytes())
            row['matches_local'] = data == local.read_bytes()
            row['matches_local_normalized'] = data.replace(b'\r\n', b'\n') == local.read_bytes().replace(b'\r\n', b'\n')
        if relative.endswith('.js'):
            row['imports'] = re.findall(r"(?:from\s+|import\s*)['\"]([^'\"]+)", data.decode('utf-8'))
        if relative == '/ui-config' and row.get('status') == 200:
            row['config'] = json.loads(data)
        if row.get('status') == 200 and row['headers'].get('etag'):
            row['conditional_etag'], _ = get(row['url'], {'If-None-Match': row['headers']['etag']})
        rows.append(row)
result = {'checked_at': datetime.now(timezone.utc).isoformat(),
          'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
          'http_assets': rows, 'scope': 'Sólo GET de HTML/assets/config; sin inferencias ni escrituras clínicas.'}
path = args.output
path.parent.mkdir(parents=True, exist_ok=True)
assert not path.exists(), 'Conservar la evidencia anterior'
path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'requests': len(rows), 'all_200': all(row.get('status') == 200 for row in rows),
                  'local_matches': all(row.get('matches_local_normalized', True) for row in rows),
                  'cache_control': {row['url']: row.get('headers', {}).get('cache-control') for row in rows[:10]}}))
