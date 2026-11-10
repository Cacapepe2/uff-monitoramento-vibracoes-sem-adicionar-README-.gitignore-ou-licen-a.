"""Consulta medicoes pela API com chave do .env, sem exibir credenciais."""
import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("-d", "--dispositivo", default="esp32-fisico-01")
    ap.add_argument("-n", "--limite", type=int, default=10)
    a = ap.parse_args()
    key = os.getenv("API_KEY", "")
    if not key:
        sys.exit("API_KEY ausente no ambiente/.env")
    try:
        r = requests.get(a.url.rstrip("/") + "/medicoes",
                         params={"dispositivo": a.dispositivo, "limite": a.limite},
                         headers={"X-API-Key": key}, timeout=5)
        print(f"GET /medicoes -> HTTP {r.status_code}")
        r.raise_for_status()
        for medicao in r.json():
            print(medicao)
        if not r.json():
            print("Nenhuma medicao desse dispositivo recebida ainda.")
    except requests.RequestException as exc:
        sys.exit(f"Falha na consulta: {exc}")


if __name__ == "__main__":
    main()
