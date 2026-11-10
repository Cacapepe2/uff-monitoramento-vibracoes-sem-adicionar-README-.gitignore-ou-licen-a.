"""Leitura e replay de dados publicos, sem SQLite, sklearn ou credenciais de escrita."""
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from cloud_sync.public_data import validate_document


BRAZIL_TIMEZONE = ZoneInfo('America/Sao_Paulo')


def brazil_time(value, chart=False):
    """Converte somente a apresentacao; graficos usam hora local sem reconversao JS."""
    if not value:
        return 'indisponível'
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None:
        raise ValueError('Timestamp sem fuso horario')
    local = instant.astimezone(BRAZIL_TIMEZONE)
    if chart:
        return local.replace(tzinfo=None).isoformat(timespec='milliseconds')
    return local.strftime('%d/%m/%Y %H:%M:%S') + ' (Brasília)'


def brazil_rows(rows):
    return [{**r, **{key: brazil_time(r[key]) for key in
                    ('instante', 'calculado_em') if r.get(key)}} for r in rows]


def bundled(path):
    raw=Path(path).read_bytes()
    if len(raw)>15_000_000: raise ValueError('Replay excede limite de tamanho')
    return validate_document(json.loads(raw))


def unpack(data):
    result={k:[] for k in ('measurement','session','membership','event','model','score','status')}
    for item in data['objects']:
        result[item['kind']].append(item['payload'])
    result['measurement'].sort(key=lambda x:(x['instante'],x['id']))
    return result


def replay_window(data,cursor):
    """Prefixo historico: nunca troca timestamps nem apresenta replay como telemetria atual."""
    result=unpack(data)
    total=len(result['measurement'])
    result['measurement']=result['measurement'][:max(0,min(cursor,total))]
    mids={x['id'] for x in result['measurement']}
    result['membership']=[x for x in result['membership'] if x['medicao_id'] in mids]
    result['score']=[x for x in result['score'] if x['medicao_id'] in mids]
    return result,total


def measurement_state(rows,now=None):
    if not rows:return 'Sem medições',None
    now=now or datetime.now(timezone.utc)
    instant=datetime.fromisoformat(rows[-1]['instante'])
    if instant.tzinfo is None:raise ValueError('Timestamp sem fuso horario')
    age=(now-instant).total_seconds()
    if age < -10:return 'Relógio inconsistente',age
    return ('Medição recente' if age<=30 else 'Sem medição recente'),age
