"""Protocolo, estados e associacao atomica por recepcao; sem acesso ao firmware."""
import json
import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

PROTOCOL_VERSION = 'experimental-v1'
PLAN = (
    ('NORMAL_01', 'Operacao normal; montagem original', 100, 100),
    ('NORMAL_02', 'Operacao normal em nova sessao independente', 50, 50),
    ('BORRACHA_01', 'Mudanca experimental da base de apoio para borracha', 50, 50),
    ('MADEIRA_01', 'Mudanca experimental de superficie rigida para madeira', 50, 50),
    ('TOQUE_01', 'Perturbacoes leves e seguras na base; registrar intervalos', None, 50),
    ('RETORNO_01', 'Restauracao da montagem original', 50, 50),
)


class ProtocolError(Exception):
    def __init__(self, message, status=409, code='conflito_protocolo'):
        self.message, self.status, self.code = message, status, code
        super().__init__(message)


def utc_now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec='microseconds')


def audit(conn, sid, action, instant, details):
    conn.execute('INSERT INTO auditoria_sessoes(sessao_id,acao,instante,detalhes) VALUES(?,?,?,?)',
                 (sid, action, instant, json.dumps(details, ensure_ascii=False)))


def get_session(conn, sid):
    row = conn.execute('SELECT * FROM sessoes_experimentais WHERE id=?', (sid,)).fetchone()
    if row is None:
        raise ProtocolError('Sessao nao encontrada', 404, 'nao_encontrado')
    return dict(row)


def get_experiment(conn, eid):
    row = conn.execute('SELECT * FROM experimentos WHERE id=?', (eid,)).fetchone()
    if row is None:
        raise ProtocolError('Experimento nao encontrado', 404, 'nao_encontrado')
    return dict(row)


def session_summary(conn, sid):
    data = get_session(conn, sid)
    counts = conn.execute('SELECT COUNT(*),COALESCE(SUM(elegivel),0) FROM medicoes_sessoes '
                          'WHERE sessao_id=?', (sid,)).fetchone()
    data.update(registros_recebidos=counts[0], registros_elegiveis=counts[1],
                registros_excluidos=counts[0]-counts[1])
    data['dados_suficientes'] = data['estado'] == 'encerrada' and counts[1] >= data['minimo_avaliacao']
    data['eventos'] = [dict(r) for r in conn.execute(
        'SELECT * FROM eventos_experimentais WHERE sessao_id=? ORDER BY inicio,id', (sid,))]
    return data


def experiment_summary(conn, eid):
    data = get_experiment(conn, eid)
    data['sessoes'] = [session_summary(conn, row[0]) for row in conn.execute(
        'SELECT id FROM sessoes_experimentais WHERE experimento_id=? ORDER BY id', (eid,)).fetchall()]
    return data


def create_experiment(conn, nome, dispositivo, observacoes=''):
    eid, instant = str(uuid4()), iso(utc_now())
    with conn:
        conn.execute('INSERT INTO experimentos VALUES(?,?,?,?,?,?)',
                     (eid, nome, dispositivo, PROTOCOL_VERSION, instant, observacoes))
        for code, description, target, minimum in PLAN:
            cur = conn.execute('INSERT INTO sessoes_experimentais(experimento_id,codigo,dispositivo,'
                'condicao_planejada,meta_registros,minimo_avaliacao,criada_em) VALUES(?,?,?,?,?,?,?)',
                (eid, code, dispositivo, description, target, minimum, instant))
            audit(conn, cur.lastrowid, 'planejada', instant, {'codigo': code})
    return experiment_summary(conn, eid)


def start_session(conn, sid, condicao, observacoes='', espera_s=10):
    conn.execute('BEGIN IMMEDIATE')
    try:
        data = get_session(conn, sid)
        if data['estado'] != 'planejada':
            raise ProtocolError('Somente sessao planejada pode ser iniciada')
        active = conn.execute("SELECT id FROM sessoes_experimentais WHERE dispositivo=? AND estado='ativa'",
                              (data['dispositivo'],)).fetchone()
        if active:
            raise ProtocolError('Ja existe sessao ativa para esse dispositivo')
        if conn.execute('SELECT 1 FROM sessoes_experimentais s JOIN modelos_ml m '
                        'ON m.experimento_id=s.experimento_id WHERE s.id=?', (sid,)).fetchone():
            # O treinamento nao impede as sessoes de avaliacao; apenas baseline e imutavel.
            if data['codigo'] == 'NORMAL_01':
                raise ProtocolError('Baseline do modelo ja foi congelada')
        now = utc_now()
        instant, collect = iso(now), iso(now + timedelta(seconds=espera_s))
        frontier = conn.execute('SELECT COALESCE(MAX(id),0) FROM medicoes').fetchone()[0]
        conn.execute("UPDATE sessoes_experimentais SET estado='ativa',condicao_observada=?,"
            'observacoes=?,inicio=?,coleta_a_partir=?,marco_inicio_id=?,espera_estabilizacao_s=? WHERE id=?',
            (condicao, observacoes, instant, collect, frontier, espera_s, sid))
        audit(conn, sid, 'iniciada', instant, {'marco_inicio_id': frontier,
              'coleta_a_partir': collect, 'espera_estabilizacao_s': espera_s})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return session_summary(conn, sid)


def end_session(conn, sid, observacoes=''):
    conn.execute('BEGIN IMMEDIATE')
    try:
        data = get_session(conn, sid)
        if data['estado'] != 'ativa':
            raise ProtocolError('Somente sessao ativa pode ser encerrada')
        if conn.execute('SELECT 1 FROM eventos_experimentais WHERE sessao_id=? AND fim IS NULL', (sid,)).fetchone():
            raise ProtocolError('Encerre o evento aberto antes de encerrar a sessao')
        instant = iso(utc_now())
        conn.execute("UPDATE sessoes_experimentais SET estado='encerrada',fim=? WHERE id=?", (instant, sid))
        audit(conn, sid, 'encerrada_manualmente', instant, {'observacoes': observacoes})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return session_summary(conn, sid)


def quality(measurement):
    for name in ('rms', 'amplitude', 'pico_fft'):
        value = measurement.get(name)
        if value is None or not math.isfinite(value) or value < 0:
            return False, f'{name}_ausente_ou_invalido'
    if measurement['pico_fft'] >= 250:
        return False, 'pico_fora_da_banda_fft'
    if measurement.get('atrasos') != 0:
        return False, 'atrasos_ausentes_ou_nao_zero'
    return True, None


def associate_received(conn, mid, measurement, instant):
    """Chamada dentro da MESMA transacao de INSERT da medicao, apos BEGIN IMMEDIATE."""
    if measurement['origem'] != 'real':
        return None
    row = conn.execute("SELECT * FROM sessoes_experimentais WHERE dispositivo=? AND estado='ativa'",
                       (measurement['dispositivo'],)).fetchone()
    if row is None or instant < row['coleta_a_partir'] or mid <= row['marco_inicio_id']:
        return None
    valid, reason = quality(measurement)
    sid = row['id']
    conn.execute('INSERT INTO medicoes_sessoes VALUES(?,?,?,?,?)', (mid, sid, instant, int(valid), reason))
    count = conn.execute('SELECT COUNT(*) FROM medicoes_sessoes WHERE sessao_id=? AND elegivel=1',
                         (sid,)).fetchone()[0]
    if row['meta_registros'] is not None and count >= row['meta_registros']:
        conn.execute("UPDATE sessoes_experimentais SET estado='encerrada',fim=? WHERE id=?", (instant, sid))
        audit(conn, sid, 'encerrada_por_meta', instant, {'elegiveis': count})
    return sid


def begin_event(conn, sid, descricao, observacoes=''):
    conn.execute('BEGIN IMMEDIATE')
    try:
        data = get_session(conn, sid)
        if data['estado'] != 'ativa' or data['codigo'] != 'TOQUE_01':
            raise ProtocolError('Eventos de perturbacao exigem TOQUE_01 ativa')
        if conn.execute('SELECT 1 FROM eventos_experimentais WHERE sessao_id=? AND fim IS NULL', (sid,)).fetchone():
            raise ProtocolError('Ja existe evento aberto nesta sessao')
        instant = iso(utc_now())
        if instant < data['coleta_a_partir']:
            raise ProtocolError('Aguarde a estabilizacao antes de registrar perturbacao')
        cur = conn.execute('INSERT INTO eventos_experimentais(sessao_id,descricao,inicio,observacoes) '
                           'VALUES(?,?,?,?)', (sid, descricao, instant, observacoes))
        audit(conn, sid, 'evento_iniciado', instant, {'evento_id': cur.lastrowid, 'descricao': descricao})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return dict(conn.execute('SELECT * FROM eventos_experimentais WHERE id=?', (cur.lastrowid,)).fetchone())


def end_event(conn, event_id):
    conn.execute('BEGIN IMMEDIATE')
    try:
        row = conn.execute('SELECT * FROM eventos_experimentais WHERE id=?', (event_id,)).fetchone()
        if row is None:
            raise ProtocolError('Evento nao encontrado', 404, 'nao_encontrado')
        if row['fim'] is not None:
            raise ProtocolError('Evento ja encerrado')
        instant = iso(utc_now())
        conn.execute('UPDATE eventos_experimentais SET fim=? WHERE id=?', (instant, event_id))
        audit(conn, row['sessao_id'], 'evento_encerrado', instant, {'evento_id': event_id})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return dict(conn.execute('SELECT * FROM eventos_experimentais WHERE id=?', (event_id,)).fetchone())


def session_measurements(conn, sid, eligible_only=False):
    get_session(conn, sid)
    sql = ('SELECT m.*,a.sessao_id,a.associada_em,a.elegivel,a.motivo_exclusao '
           'FROM medicoes m JOIN medicoes_sessoes a ON m.id=a.medicao_id WHERE a.sessao_id=?')
    if eligible_only:
        sql += ' AND a.elegivel=1'
    return [dict(r) for r in conn.execute(sql+' ORDER BY m.instante,m.id', (sid,))]
