"""Outbox em banco separado: reenvio, lease e ACK por revisao, sem tocar no SQLite cientifico."""
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4


class Queue:
    def __init__(self, path, source_id=None):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS outbox(kind TEXT,entity_id TEXT,payload TEXT,hash TEXT,revision INTEGER,
                ack INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,due REAL NOT NULL DEFAULT 0,
                lease REAL NOT NULL DEFAULT 0,owner TEXT,PRIMARY KEY(kind,entity_id));''')
            existing = c.execute("SELECT value FROM settings WHERE key='source_id'").fetchone()
            if existing and source_id and existing[0] != source_id:
                raise ValueError('SOURCE_ID difere do estado local; nao reutilizar outbox de outra origem')
            self.source_id = existing[0] if existing else str(source_id or uuid4())
            UUID(self.source_id)
            c.execute("INSERT OR IGNORE INTO settings VALUES('source_id',?)", (self.source_id,))

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def scan(self, objects):
        changed = 0
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            for kind, eid, payload in objects:
                raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
                digest = hashlib.sha256(raw.encode()).hexdigest()
                row = c.execute('SELECT hash,revision FROM outbox WHERE kind=? AND entity_id=?',(kind,eid)).fetchone()
                if row and row['hash'] == digest:
                    continue
                revision = row['revision']+1 if row else 1
                c.execute('''INSERT INTO outbox(kind,entity_id,payload,hash,revision) VALUES(?,?,?,?,?)
                    ON CONFLICT(kind,entity_id) DO UPDATE SET payload=excluded.payload,hash=excluded.hash,
                    revision=excluded.revision,due=0,attempts=0''',(kind,eid,raw,digest,revision))
                changed += 1
        return changed

    def claim(self, limit=100, now=None):
        now = time.time() if now is None else now
        owner = str(uuid4())
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            rows = c.execute('SELECT * FROM outbox WHERE revision>ack AND due<=? AND lease<=? '
                             'ORDER BY kind,entity_id LIMIT ?', (now,now,limit)).fetchall()
            for row in rows:
                c.execute('UPDATE outbox SET lease=?,owner=? WHERE kind=? AND entity_id=?',
                          (now+120,owner,row['kind'],row['entity_id']))
        return [{**dict(r),'owner':owner} for r in rows]

    def finish(self, batch, success, now=None):
        now = time.time() if now is None else now
        with self.connect() as c:
            for r in batch:
                if success:
                    c.execute('UPDATE outbox SET ack=MAX(ack,?),attempts=0,due=0,lease=0,owner=NULL '
                        'WHERE kind=? AND entity_id=? AND owner=?', (r['revision'],r['kind'],r['entity_id'],r['owner']))
                else:
                    delay = min(300, 5*2**min(r['attempts'],6))
                    c.execute('UPDATE outbox SET attempts=attempts+1,due=?,lease=0,owner=NULL '
                        'WHERE kind=? AND entity_id=? AND owner=?', (now+delay,r['kind'],r['entity_id'],r['owner']))
            if success and batch:
                c.execute("INSERT INTO settings VALUES('last_success_at',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(now),))

    def status(self):
        with self.connect() as c:
            row=c.execute('SELECT COUNT(*),COALESCE(SUM(revision>ack),0),COALESCE(SUM(revision>ack AND attempts>0),0) FROM outbox').fetchone()
            last=c.execute("SELECT value FROM settings WHERE key='last_success_at'").fetchone()
        return {'source_id':self.source_id,'total':row[0],'pending':row[1],'failed':row[2],
                'last_success_at':float(last[0]) if last else None}
