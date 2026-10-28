"""Busca hasta dos fragmentos de un paciente con el modelo de embeddings común."""

import argparse
import json

from app.knowledge import search_fragments


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patient_id", type=int)
    parser.add_argument("question")
    args = parser.parse_args()
    try:
        print(json.dumps(search_fragments(args.patient_id, args.question), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f"No se pudo completar la búsqueda: {error}\n")
