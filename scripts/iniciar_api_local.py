"""Inicia a demonstracao em rede local somente com X-API-Key configurada."""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from dotenv import load_dotenv

from backend.database import ROOT
from backend.main import create_app


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="0.0.0.0", help="IPv4 local de escuta (padrao: 0.0.0.0)")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")
    key = os.getenv("API_KEY", "")
    if not key.strip() or key == "troque-por-uma-chave-longa-e-aleatoria":
        sys.exit("Configure API_KEY no .env antes de iniciar a demonstracao na rede local.")
    uvicorn.run(create_app(api_key=key), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
