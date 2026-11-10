"""Checklist somente leitura para a apresentacao; nao imprime credenciais ou IPs."""
import argparse
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests
from dotenv import load_dotenv
from backend.database import resolve_db_path
from cloud_sync.public_data import FIELDS
from cloud_sync.transport import Supabase
from dashboard.public_view import brazil_time

PUBLIC_URL = 'https://tvxmuwbubmciksacfqwcrw.streamlit.app/'


def readonly(path):
    c = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def latest(device):
    c = readonly(resolve_db_path())
    try:
        row = c.execute("SELECT * FROM medicoes WHERE origem='real' AND dispositivo=? "
                        'ORDER BY id DESC LIMIT 1', (device,)).fetchone()
        return dict(row) if row else None
    finally:
        c.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--espera', type=int, default=12, choices=range(0, 61), metavar='0..60',
                        help='Segundos para observar novas medicoes (padrao: 12)')
    parser.add_argument('--dispositivo', default='esp32-fisico-01')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    warnings = 0

    def result(ok, message):
        nonlocal warnings
        warnings += not ok
        print(('[OK] ' if ok else '[ATENCAO] ') + message, flush=True)

    session = requests.Session()
    session.trust_env = False
    before = None
    try:
        c = readonly(resolve_db_path())
        try:
            result(c.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'SQLite: verificacao de integridade')
        finally:
            c.close()
        before = latest(args.dispositivo)
        result(before is not None, 'Historico real encontrado no SQLite')
        if before:
            print(f"     Ultimo ID {before['id']} em {brazil_time(before['instante'])}", flush=True)
    except Exception:
        result(False, 'SQLite indisponivel; conferir DB_PATH e arquivo local')

    try:
        r = session.get('http://127.0.0.1:8000/health', timeout=(3, 5))
        d = r.json()
        result(r.status_code == 200 and d.get('banco') == 'ok' and d.get('auth') is True,
               'FastAPI: HTTP 200, banco disponivel e autenticacao ativa')
        key = os.getenv('API_KEY', '')
        if not key:
            result(False, 'API_KEY ausente; nenhum valor foi exibido')
        else:
            r = session.get('http://127.0.0.1:8000/medicoes',
                params={'dispositivo': args.dispositivo, 'limite': 1},
                headers={'X-API-Key': key}, timeout=(3, 5))
            r.raise_for_status()
            rows = r.json()
            if rows:
                c = readonly(resolve_db_path())
                try:
                    stored = c.execute('SELECT * FROM medicoes WHERE id=?', (rows[0]['id'],)).fetchone()
                    result(stored is not None and all(stored[k] == v for k, v in rows[0].items()),
                           f"Consulta autenticada: ID {rows[0]['id']} igual ao SQLite")
                finally:
                    c.close()
            else:
                result(False, 'API ainda sem medicoes deste dispositivo')
    except Exception:
        result(False, 'API/consulta indisponivel; conferir processo, chave e porta 8000')

    if args.espera:
        print(f'Aguardando {args.espera} s para observar novos IDs reais...', flush=True)
        time.sleep(args.espera)
        try:
            after = latest(args.dispositivo)
            fresh = after is not None and (before is None or after['id'] > before['id'])
            result(fresh, 'Novas medicoes reais chegaram durante a observacao' if fresh else
                   'Nenhum novo ID: conferir USB, Serial, Wi-Fi, IP da API e firewall; historico nao comprova sensor ativo')
        except Exception:
            result(False, 'Nao foi possivel observar novos IDs')

    try:
        c = readonly(ROOT / '.marco3_local/cloud_queue.db')
        try:
            state = c.execute('SELECT COALESCE(SUM(revision>ack),0), '
                              'COALESCE(SUM(revision>ack AND attempts>0),0) FROM outbox').fetchone()
            stamp = c.execute("SELECT value FROM settings WHERE key='last_success_at'").fetchone()
            recent = bool(stamp) and 0 <= time.time() - float(stamp[0]) <= 60
            result(state[1] == 0 and recent,
                   f'Sincronizador: {state[0]} pendentes, {state[1]} com falha; '
                   + ('sucesso nos ultimos 60 s' if recent else 'sem sucesso recente; conferir worker e internet'))
        finally:
            c.close()
    except Exception:
        result(False, 'Estado da fila indisponivel; a checagem nao criou nem alterou a outbox')

    try:
        remote = Supabase(os.getenv('SUPABASE_URL', ''), os.getenv('SUPABASE_PUBLISHABLE_KEY', ''))
        if before:
            r = remote.session.get(remote.url + '/rest/v1/vibration_objects', headers=remote.headers,
                params={'source_id': 'eq.' + os.getenv('CLOUD_SOURCE_ID', ''), 'kind': 'eq.measurement',
                        'entity_id': 'eq.' + str(before['id']), 'select': 'payload'}, timeout=(5, 10))
            r.raise_for_status()
            rows = r.json()
            result(len(rows) == 1 and rows[0]['payload'] == {k: before[k] for k in FIELDS['measurement']},
                   f"Supabase publico: ID {before['id']} e dados iguais ao SQLite")
        r = session.get(PUBLIC_URL + '_stcore/health', timeout=(5, 10))
        result(r.status_code == 200, 'Streamlit publico: endpoint de saude HTTP 200 (conferir metricas no navegador)')
    except Exception:
        result(False, 'Consulta publica indisponivel; conferir internet, configuracao e modo Replay')

    print(f'Checagem concluida: {warnings} item(ns) requerem atencao. Nenhum dado ou servico foi alterado.', flush=True)
    return 1 if warnings else 0


if __name__ == '__main__':
    raise SystemExit(main())
