"""Cache incremental de leitura publica; estado compartilhado protegido por lock."""
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic

from cloud_sync.public_data import validate_document


class IncrementalReader:
    def __init__(self, remote, source, full_refresh_seconds=300, max_objects=20000):
        self.remote = remote
        self.source = source
        self.full_refresh_seconds = full_refresh_seconds
        self.max_objects = max_objects
        self.objects = {}
        self.watermark = None
        self.last_full = None
        self.lock = Lock()

    def read(self):
        with self.lock:
            now = monotonic()
            full = (self.last_full is None or self.watermark is None or
                    now - self.last_full >= self.full_refresh_seconds)
            if full:
                rows = self.remote.read(self.source)
                merged = {}
            else:
                # Sobreposicao cobre empates e transacoes recentes; merge por identidade.
                since = (self.watermark - timedelta(seconds=120)).isoformat()
                rows = self.remote.read(self.source, since=since)
                merged = dict(self.objects)
            for row in rows:
                merged[(row['kind'], row['entity_id'])] = row
            if len(merged) > self.max_objects:
                raise ValueError('Limite de objetos do painel atingido')
            data = validate_document({'schema_version': 1, 'source_id': self.source,
                'objects': list(merged.values()),
                'fetched_at': datetime.now(timezone.utc).isoformat()})
            # Commit local apenas depois de validar toda a resposta.
            stamps = [datetime.fromisoformat(r['received_at']) for r in merged.values()
                      if r.get('received_at')]
            if any(t.tzinfo is None for t in stamps):
                raise ValueError('Timestamp remoto sem fuso horario')
            self.objects = merged
            self.watermark = max(stamps) if stamps else None
            if full:
                self.last_full = now
            return data
