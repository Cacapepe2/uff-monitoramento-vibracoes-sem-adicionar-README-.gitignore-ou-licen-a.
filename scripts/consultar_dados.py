"""Consulta o SQLite diretamente (sem passar pela API).

Exemplos:
  python scripts/consultar_dados.py                    # ultimas 10
  python scripts/consultar_dados.py -n 50
  python scripts/consultar_dados.py -d esp32-wokwi-01  # filtra dispositivo
  python scripts/consultar_dados.py --resumo           # contagem por cenario
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.database import resolve_db_path  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("-n", "--limite", type=int, default=10)
    ap.add_argument("-d", "--dispositivo")
    ap.add_argument("--resumo", action="store_true")
    ap.add_argument("--db", help="caminho do banco (padrao: dados/medicoes.db)")
    a = ap.parse_args()

    path = resolve_db_path(a.db)
    if not path.exists():
        sys.exit(f"Banco nao encontrado: {path} (inicie a API ao menos uma vez)")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    if a.resumo:
        rows = conn.execute("SELECT dispositivo, cenario, COUNT(*) n, ROUND(AVG(rpm),1) rpm_medio, "
                            "ROUND(AVG(amplitude),4) amp_media FROM medicoes "
                            "GROUP BY dispositivo, cenario ORDER BY dispositivo, cenario").fetchall()
    else:
        sql, args = "SELECT * FROM medicoes", []
        if a.dispositivo:
            sql += " WHERE dispositivo = ?"
            args.append(a.dispositivo)
        sql += " ORDER BY instante DESC, id DESC LIMIT ?"
        args.append(a.limite)
        rows = conn.execute(sql, args).fetchall()

    if not rows:
        print("Nenhum registro.")
        return
    cols = rows[0].keys()
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join(str(r[c]) for c in cols))
    print(f"({len(rows)} linha(s))  banco: {path}")


if __name__ == "__main__":
    main()
