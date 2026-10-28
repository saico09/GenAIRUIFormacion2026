"""Crea la colección solo si falta y verifica dimensión y distancia."""

import json

from app.knowledge import prepare_collection

if __name__ == "__main__":
    print(json.dumps(prepare_collection(), ensure_ascii=False, indent=2))
