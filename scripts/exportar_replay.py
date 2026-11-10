"""Exporta apenas medicoes reais com sessao; nao altera timestamps, modelos ou SQLite."""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
from backend.database import resolve_db_path
from cloud_sync.public_data import document,read_objects,validate_document
from cloud_sync.queue import Queue


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--saida',type=Path,default=ROOT/'dashboard/data/replay.json')
    args=ap.parse_args();load_dotenv(ROOT/'.env')
    if args.saida.exists():sys.exit('Replay existente preservado; use --saida com novo caminho para outra exportacao.')
    q=Queue(ROOT/'.marco3_local/cloud_queue.db',os.getenv('CLOUD_SOURCE_ID'))
    objects=read_objects(resolve_db_path())
    mids={p['medicao_id'] for k,i,p in objects if k=='membership'}
    objects=[(k,i,p) for k,i,p in objects if k!='measurement' or p['id'] in mids]
    data=validate_document(document(objects,q.source_id,datetime.now(timezone.utc).isoformat()))
    args.saida.parent.mkdir(parents=True,exist_ok=True)
    args.saida.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    digest=hashlib.sha256(args.saida.read_bytes()).hexdigest()
    print('Replay historico exportado:',len(mids),'medicoes reais com sessao. SHA256:',digest)


if __name__=='__main__':main()
