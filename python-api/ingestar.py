"""Lee informes confirmados y sincroniza sus fragmentos sin duplicar registros."""

import argparse
from collections import Counter
import json
from pathlib import Path

from app.history_documents import fragments_from_history, load_histories
from app.history_index import index_history, patient_points
from app.knowledge import COLLECTION, qdrant


def load_fragments(data_dir: Path) -> list[dict]:
    return [fragment for history in load_histories(data_dir) for fragment in fragments_from_history(history)]


def verify_fragments(fragments: list[dict]) -> dict:
    expected = {fragment['id']: fragment['payload'] for fragment in fragments}
    patients = sorted({payload['patient_id'] for payload in expected.values()})
    stored = {point['id']: point['payload'] for patient_id in patients for point in patient_points(patient_id)}
    if stored != expected:
        raise ValueError('Los puntos no coinciden con los informes confirmados')
    total = qdrant('POST', f'/collections/{COLLECTION}/points/count', {'exact': True})['result']['count']
    return {'collection': COLLECTION, 'count': len(stored), 'collection_count': total,
            'per_patient': dict(sorted(Counter(payload['patient_id'] for payload in stored.values()).items())),
            'payloads_match': True, 'example': fragments[0] if fragments else None}


def ingest(data_dir: Path) -> dict:
    histories = load_histories(data_dir)  # Validar todo el corpus antes de escribir.
    results = [index_history(history) for history in histories]
    fragments = [fragment for history in histories for fragment in fragments_from_history(history)]
    return {**verify_fragments(fragments), 'histories': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('/datos/historias'))
    args = parser.parse_args()
    try:
        print(json.dumps(ingest(args.data_dir), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f'No se pudo completar la ingesta: {error}\n')
