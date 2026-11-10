"""Fixtures de SOFTWARE em bancos temporarios; nao sao medicoes fisicas coletadas."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend import database, experiments
from backend.main import create_app

H = {'X-API-Key': 'teste-experimental'}
REAL = dict(dispositivo='esp32-fisico-01', origem='real', pico_fft=50.78125,
            amplitude=.2, rms=.1, atrasos=0)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)

    def advance(self, seconds=6):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(experiments, 'utc_now', lambda: clock.now)
    db = tmp_path/'experiment.db'
    client = TestClient(create_app(db_path=db, api_key=H['X-API-Key']))
    result = client.post('/experimentos', headers=H,
                         json={'nome':'FIXTURE de software; sem hardware'}).json()
    return client, db, clock, result


def sid(exp, code):
    return next(s['id'] for s in exp['sessoes'] if s['codigo']==code)


def start(client, exp, code, wait=0):
    return client.post(f"/sessoes/{sid(exp,code)}/iniciar", headers=H,
                      json={'condicao':'FIXTURE: condicao somente para teste',
                            'espera_estabilizacao_s':wait})


def send(client, clock, i=0, shift=0, **changes):
    clock.advance()
    body = {**REAL, 'rms':.1+(i%11)*.003+shift,
            'amplitude':.2+(i%7)*.004+shift, 'pico_fft':50.78125+(i%3)*1.953125,
            **changes}
    response = client.post('/medicoes', json=body, headers=H)
    assert response.status_code==201, response.text
    return response.json()


def collect(client, clock, exp, code, count, shift=0):
    assert start(client, exp, code).status_code==200
    return [send(client, clock, i, shift=shift)['id'] for i in range(count)]


def test_planejamento_sem_medicoes_e_autenticacao(rig):
    client, db, clock, exp = rig
    assert [s['meta_registros'] for s in exp['sessoes']]==[100,50,50,50,None,50]
    assert all(s['estado']=='planejada' and s['registros_recebidos']==0 for s in exp['sessoes'])
    assert client.get('/experimentos').status_code==401
    assert client.post('/experimentos',json={'nome':'outro'}).status_code==401
    assert client.post(f"/sessoes/{sid(exp,'NORMAL_01')}/iniciar",json={'condicao':'abc'}).status_code==401
    with closing(database.connect(db)) as conn:
        assert conn.execute('select count(*) from medicoes').fetchone()[0]==0


def test_sem_rotulo_retroativo_dispositivo_origem_e_guarda(rig):
    client, db, clock, exp = rig
    old = send(client,clock)['id']
    assert start(client,exp,'NORMAL_01',wait=10).status_code==200
    guard = send(client,clock)['id']  # +6 s: ainda dentro da guarda
    new = send(client,clock)['id']    # +12 s
    other = send(client,clock,dispositivo='outro')['id']
    synthetic = send(client,clock,origem='simulacao',rpm=3000,frequencia_1x=50,cenario=0)['id']
    for mid in (old,guard,other,synthetic):
        assert client.get(f'/medicoes/{mid}/sessao',headers=H).json() is None
    assoc=client.get(f'/medicoes/{new}/sessao',headers=H).json()
    assert assoc['sessao_id']==sid(exp,'NORMAL_01') and assoc['elegivel']==1
    with closing(database.connect(db)) as conn:
        with pytest.raises(sqlite3.IntegrityError,match='retroativa'):
            conn.execute('INSERT INTO medicoes_sessoes VALUES(?,?,?,?,?)',
                          (old,sid(exp,'NORMAL_01'),experiments.iso(clock.now),1,None))
    assert client.post('/medicoes',headers=H,json={**REAL,'sessao_id':sid(exp,'NORMAL_01')}).status_code==422


def test_transicoes_e_um_dispositivo_nao_mistura_sessoes(rig):
    client, db, clock, exp=rig
    assert start(client,exp,'NORMAL_01').status_code==200
    assert start(client,exp,'NORMAL_01').status_code==409
    assert start(client,exp,'NORMAL_02').status_code==409
    other=client.post('/experimentos',headers=H,json={'nome':'outra campanha'}).json()
    assert start(client,other,'NORMAL_01').status_code==409
    end=client.post(f"/sessoes/{sid(exp,'NORMAL_01')}/encerrar",headers=H,json={'observacoes':'teste parcial'})
    assert end.status_code==200 and not end.json()['dados_suficientes']
    assert start(client,exp,'NORMAL_01').status_code==409
    assert client.post(f"/sessoes/{sid(exp,'NORMAL_01')}/encerrar",headers=H,json={}).status_code==409
    assert start(client,exp,'NORMAL_02').status_code==200
    audit=client.get(f"/sessoes/{sid(exp,'NORMAL_01')}",headers=H).json()['auditoria']
    assert audit[-1]['detalhes']['observacoes']=='teste parcial'


def test_inicios_concorrentes_apenas_um_vence(rig):
    client, db, clock, exp=rig
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda c:start(client,exp,c).status_code,['NORMAL_01','NORMAL_02']))
    assert sorted(results)==[200,409]


@pytest.mark.parametrize('changes,reason',[
    ({'rms':None},'rms_ausente'), ({'atrasos':None},'atrasos_ausentes'),
    ({'atrasos':1},'atrasos_ausentes'), ({'pico_fft':300},'pico_fora'),
])
def test_qualidade_registra_exclusao_sem_inventar_valores(rig,changes,reason):
    client,db,clock,exp=rig
    start(client,exp,'NORMAL_01')
    mid=send(client,clock,**changes)['id']
    result=client.get(f'/medicoes/{mid}/sessao',headers=H).json()
    assert result['elegivel']==0 and result['motivo_exclusao'].startswith(reason)
    status=client.get(f"/sessoes/{sid(exp,'NORMAL_01')}",headers=H).json()
    assert status['registros_recebidos']==1 and status['registros_elegiveis']==0


def test_meta_encerra_exatamente_sem_associar_proximos(rig):
    client,db,clock,exp=rig
    ids=collect(client,clock,exp,'NORMAL_01',100)
    extra=send(client,clock)['id']
    s=client.get(f"/sessoes/{sid(exp,'NORMAL_01')}",headers=H).json()
    assert s['estado']=='encerrada' and s['registros_elegiveis']==100
    assert s['dados_suficientes'] and s['auditoria'][-1]['acao']=='encerrada_por_meta'
    assert client.get(f'/medicoes/{extra}/sessao',headers=H).json() is None
    rows=client.get(f"/sessoes/{s['id']}/medicoes",headers=H).json()
    assert [r['id'] for r in rows]==ids
    with closing(database.connect(db)) as conn:
        with pytest.raises(sqlite3.IntegrityError,match='imutavel'):
            conn.execute('UPDATE medicoes SET rms=99 WHERE id=?',(ids[0],))
        with pytest.raises(sqlite3.IntegrityError,match='imutavel'):
            conn.execute('UPDATE medicoes_sessoes SET sessao_id=999 WHERE medicao_id=?',(ids[0],))
        with pytest.raises(sqlite3.IntegrityError,match='imutavel'):
            conn.execute('DELETE FROM medicoes WHERE id=?',(ids[0],))


def test_rollback_ingestao_e_associacao_atomicas(rig,monkeypatch):
    client,db,clock,exp=rig
    start(client,exp,'NORMAL_01')
    def fail(*args):raise sqlite3.OperationalError('fixture: falha de associacao')
    monkeypatch.setattr(experiments,'associate_received',fail)
    r=client.post('/medicoes',json=REAL,headers=H)
    assert r.status_code==500
    with closing(database.connect(db)) as conn:
        assert conn.execute('SELECT COUNT(*) FROM medicoes').fetchone()[0]==0


def test_eventos_exigem_toque_ativo_sem_sobreposicao(rig):
    client,db,clock,exp=rig
    assert client.post(f"/sessoes/{sid(exp,'TOQUE_01')}/eventos",headers=H,
                       json={'descricao':'toque fixture'}).status_code==409
    assert start(client,exp,'TOQUE_01',wait=10).status_code==200
    endpoint=f"/sessoes/{sid(exp,'TOQUE_01')}/eventos"
    assert client.post(endpoint,headers=H,json={'descricao':'toque fixture'}).status_code==409
    clock.advance(11)
    event=client.post(endpoint,headers=H,json={'descricao':'perturbacao fixture'}).json()
    assert event['inicio'].endswith('+00:00')
    assert client.post(endpoint,headers=H,json={'descricao':'sobreposto'}).status_code==409
    assert client.post(f"/sessoes/{sid(exp,'TOQUE_01')}/encerrar",headers=H,json={}).status_code==409
    clock.advance(2)
    ended=client.post(f"/eventos/{event['id']}/encerrar",headers=H).json()
    assert ended['fim']>ended['inicio']
    assert client.post(f"/eventos/{event['id']}/encerrar",headers=H).status_code==409
    assert client.post(f"/sessoes/{sid(exp,'TOQUE_01')}/encerrar",headers=H,json={}).status_code==200


@pytest.mark.parametrize('body',[
    {'condicao':'   '}, {'condicao':'ok?', 'espera_estabilizacao_s':-1},
    {'condicao':'ok?', 'espera_estabilizacao_s':True},
    {'condicao':'ok?', 'inicio':'2020-01-01T00:00:00Z'},
])
def test_inicio_sem_descricao_ou_com_campos_invalidos_recusado(rig,body):
    client,db,clock,exp=rig
    assert client.post(f"/sessoes/{sid(exp,'NORMAL_01')}/iniciar",headers=H,json=body).status_code==422


def test_evento_nao_aceita_horario_retroativo(rig):
    client,db,clock,exp=rig
    start(client,exp,'TOQUE_01')
    assert client.post(f"/sessoes/{sid(exp,'TOQUE_01')}/eventos",headers=H,
        json={'descricao':'fixture','inicio':'2020-01-01T00:00:00Z'}).status_code==422


def test_migracao_aditiva_preserva_banco_anterior_sem_rotulos(tmp_path):
    from backend.models import SCHEMA
    db=tmp_path/'anterior.db'
    with closing(sqlite3.connect(db)) as conn:
        conn.executescript(SCHEMA)
        conn.execute('INSERT INTO medicoes(instante,dispositivo,pico_fft,amplitude,origem,rms,atrasos) '
                     "VALUES('2026-11-03T00:00:00+00:00','legado',50,.2,'real',.1,0)")
        conn.commit();before=conn.execute('SELECT * FROM medicoes').fetchall()
    database.init_db(db)
    database.init_db(db)
    with closing(database.connect(db)) as conn:
        assert [tuple(r) for r in conn.execute('SELECT * FROM medicoes')]==before
        assert conn.execute('SELECT COUNT(*) FROM medicoes_sessoes').fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM experimentos').fetchone()[0]==0
        assert conn.execute('pragma foreign_key_check').fetchall()==[]
        assert conn.execute('pragma integrity_check').fetchone()[0]=='ok'
    assert len(list(tmp_path.glob('*.pre-experimentos-*.bak')))==1
