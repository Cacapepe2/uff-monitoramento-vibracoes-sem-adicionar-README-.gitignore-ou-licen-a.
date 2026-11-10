"""Respostas isoladas: nenhum dado de teste e enviado a nuvem."""
from copy import deepcopy
from pathlib import Path

import pytest

from dashboard.cloud_reader import IncrementalReader
from dashboard.public_view import bundled


def sample():
    data = bundled(Path(__file__).resolve().parent.parent / 'dashboard/data/replay.json')
    row = deepcopy(next(r for r in data['objects'] if r['kind'] == 'measurement'))
    row['received_at'] = '2026-11-10T13:00:00+00:00'
    return row


def test_incremental_atualiza_por_id_sem_duplicar_e_preserva_em_falha():
    first = sample()
    changed = deepcopy(first)
    changed['payload']['rms'] = 0.75
    changed['received_at'] = '2026-11-10T13:01:00+00:00'
    new = deepcopy(changed)
    new['entity_id'] = '999999'
    new['payload']['id'] = 999999

    class Remote:
        calls = []
        offline = False

        def read(self, source, since=None):
            self.calls.append(since)
            if self.offline:
                raise TimeoutError('fixture offline')
            return deepcopy([first] if since is None else [changed, new])

    remote = Remote()
    reader = IncrementalReader(remote, 'fixture')
    assert len(reader.read()['objects']) == 1
    result = reader.read()
    assert remote.calls == [None, '2026-11-10T12:58:00+00:00']
    assert len(result['objects']) == 2
    assert result['objects'][0]['payload']['rms'] == 0.75
    assert len(reader.read()['objects']) == 2
    saved = deepcopy(reader.objects)
    remote.offline = True
    with pytest.raises(TimeoutError):
        reader.read()
    assert reader.objects == saved


def test_reconciliacao_completa_periodica_remove_objetos_ausentes():
    class Remote:
        rows = [sample()]
        calls = []

        def read(self, source, since=None):
            self.calls.append(since)
            return deepcopy(self.rows)

    remote = Remote()
    reader = IncrementalReader(remote, 'fixture', full_refresh_seconds=0)
    assert len(reader.read()['objects']) == 1
    remote.rows = []
    assert reader.read()['objects'] == []
    assert remote.calls == [None, None]


def test_filtro_incremental_recebido_pelo_transporte():
    from cloud_sync.transport import Supabase

    class Response:
        status_code = 200

        def json(self):
            return []

    class Session:
        def get(self, url, **kwargs):
            self.params = kwargs['params']
            return Response()

    session = Session()
    remote = Supabase('https://fixture.supabase.co', 'sb_publishable_fixture', session)
    assert remote.read('fixture', since='2026-11-10T13:00:00+00:00') == []
    assert session.params['received_at'] == 'gte.2026-11-10T13:00:00+00:00'
    assert session.params['order'] == 'received_at,kind,entity_id'
