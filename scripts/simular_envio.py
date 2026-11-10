"""Envia medicoes sinteticas a API, sem precisar do ESP32/Wokwi.

  python scripts/simular_envio.py                       # localhost:8000
  python scripts/simular_envio.py --url https://xxxx.trycloudflare.com
A chave vem de --api-key ou da variavel de ambiente API_KEY (.env).
"""
import argparse
import os
import random
import sys
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# (cenario, amplitude tipica do pico) - valores SINTETICOS
CENARIOS = {0: ("normal", 0.08), 1: ("desbalanceamento", 0.50), 2: ("desalinhamento", 0.40)}


def gerar(cenario: int, dispositivo: str) -> dict:
    _, amp = CENARIOS[cenario]
    rpm = random.gauss(3009, 6)
    f1 = rpm / 60
    pico = f1 * (2 if cenario == 2 else 1) + random.uniform(-0.6, 0.6)
    return {"dispositivo": dispositivo, "rpm": round(rpm, 1), "frequencia_1x": round(f1, 2),
            "pico_fft": round(pico, 2), "amplitude": round(amp * random.uniform(0.9, 1.1), 4),
            "cenario": cenario, "origem": "simulacao"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--api-key", default=os.getenv("API_KEY", ""))
    ap.add_argument("--dispositivo", default="simulador-python")
    ap.add_argument("-n", type=int, default=3, help="registros por cenario")
    a = ap.parse_args()
    url = a.url.rstrip("/")
    headers = {"X-API-Key": a.api_key} if a.api_key else {}

    erros = 0
    try:
        for cen in CENARIOS:
            for _ in range(a.n):
                body = gerar(cen, a.dispositivo)
                r = requests.post(f"{url}/medicoes", json=body, headers=headers, timeout=10)
                print(f"POST cenario={cen} ({CENARIOS[cen][0]}) -> HTTP {r.status_code} {r.text}")
                erros += r.status_code != 201
        r = requests.get(f"{url}/medicoes", params={"limite": 5, "dispositivo": a.dispositivo},
                         headers=headers, timeout=10)
        print(f"\nGET /medicoes?limite=5 -> HTTP {r.status_code}")
        if r.ok:
            for m in r.json():
                print(" ", m)
    except requests.exceptions.RequestException as e:
        sys.exit(f"Erro de conexao com {url}: {e}\nA API esta rodando? O tunel esta ativo?")
    sys.exit(1 if erros else 0)


if __name__ == "__main__":
    main()
