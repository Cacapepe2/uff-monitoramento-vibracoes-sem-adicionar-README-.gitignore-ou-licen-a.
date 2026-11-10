"""Mostra a consulta SQL e o resultado em tabela para evidencias dos Marcos 2 e 3.

  python scripts/print_banco.py                 # dispositivo esp32-wokwi-01, 10 linhas
  python scripts/print_banco.py -d simulador-python -n 5
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.database import resolve_db_path  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("-d", "--dispositivo", default="esp32-wokwi-01")
ap.add_argument("-n", "--limite", type=int, default=10)
ap.add_argument("--db", help="caminho do banco (padrao: dados/medicoes.db)")
a = ap.parse_args()

path = resolve_db_path(a.db)
if not path.exists():
    sys.exit(f"Banco nao encontrado: {path}")
conn = sqlite3.connect(path)
# Tambem permite capturar o banco antigo antes de iniciar a API/migracao.
columns = {r[1] for r in conn.execute("PRAGMA table_info(medicoes)")}
extras = ", ".join(name if name in columns else f"NULL AS {name}" for name in ("rms", "atrasos"))
sql = (f"SELECT id, instante, dispositivo, rpm, pico_fft, amplitude, cenario, origem, {extras} "
       "FROM medicoes WHERE dispositivo = ? ORDER BY id DESC LIMIT ?")
rows = conn.execute(sql, (a.dispositivo, a.limite)).fetchall()
head = ["id", "instante (UTC)", "dispositivo", "rpm", "pico_fft", "amplitude", "cen", "origem", "rms", "atrasos"]

print(f"Banco: {path.name}  |  tabela: medicoes")
print(f"SQL> SELECT id, instante, dispositivo, rpm, pico_fft, amplitude, cenario, origem, {extras}\n"
      f"     FROM medicoes WHERE dispositivo = '{a.dispositivo}' ORDER BY id DESC LIMIT {a.limite};\n")
w = [max(len(str(x)) for x in col) for col in zip(head, *rows)] if rows else [len(h) for h in head]
fmt = lambda r: " | ".join(str(v).ljust(n) for v, n in zip(r, w))
print(fmt(head))
print("-+-".join("-" * n for n in w))
for r in rows:
    print(fmt(r))
total = conn.execute("SELECT COUNT(*) FROM medicoes").fetchone()[0]
print(f"\n({len(rows)} linhas exibidas | total na tabela: {total})")
conn.close()
