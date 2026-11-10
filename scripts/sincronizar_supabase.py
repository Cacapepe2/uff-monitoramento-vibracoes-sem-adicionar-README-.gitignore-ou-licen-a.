"""Worker independente. Sem configuracao, apenas prepara fila local; nao envia nada."""
import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
from backend.database import resolve_db_path
from cloud_sync.public_data import read_objects
from cloud_sync.queue import Queue
from cloud_sync.transport import Supabase


def cycle(queue, db, remote=None, email=None, password=None):
    queue.scan(read_objects(db))
    state=queue.status()
    stamp=lambda t: datetime.fromtimestamp(t,timezone.utc).isoformat() if t else None
    queue.scan([('status','sync',{'last_success_at':stamp(state['last_success_at']),
        'pending':state['pending'],'failed':state['failed'],'checked_at':stamp(time.time())})])
    if remote:
        batch=queue.claim()
        if batch:
            try:
                if not remote.token or time.time()>=remote.expires:
                    remote.login(email,password)
                remote.send(queue.source_id,batch)
            except Exception:
                queue.finish(batch,False)
                print('Lote sem confirmacao; retentativa com backoff. Detalhes sensiveis omitidos.',flush=True)
            else:
                queue.finish(batch,True)
    return queue.status()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--loop',action='store_true')
    parser.add_argument('--local-only',action='store_true',help='Preparar fila sem conexao externa')
    parser.add_argument('--status',action='store_true')
    parser.add_argument('--state',type=Path,default=ROOT/'.marco3_local/cloud_queue.db')
    args=parser.parse_args(); load_dotenv(ROOT/'.env')
    q=Queue(args.state,os.getenv('CLOUD_SOURCE_ID'))
    if args.status:
        print(q.status());return
    names=['SUPABASE_URL','SUPABASE_PUBLISHABLE_KEY','SUPABASE_SYNC_EMAIL','SUPABASE_SYNC_PASSWORD']
    ready=all(os.getenv(k) for k in names)
    remote=None if args.local_only or not ready else Supabase(os.environ[names[0]],os.environ[names[1]])
    if not remote: print('Modo local: nenhuma sincronizacao remota executada.')
    try:
        while True:
            state=cycle(q,resolve_db_path(),remote,os.getenv(names[2]),os.getenv(names[3]))
            print('Fila:',state,flush=True)
            if not args.loop:return
            time.sleep(5)
    except KeyboardInterrupt:
        print('Worker encerrado; fila e SQLite preservados.')


if __name__=='__main__': main()
