"""Dados desta suite sao fixtures isoladas, nao evidencia de performance fisica."""
import json
import math
import pickle
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip('sklearn')

from analytics.isolation import event_metrics, event_phase
from analytics.visualization import charts, write_html
from backend.database import connect
from backend.main import create_app
from fastapi.testclient import TestClient
from test_experimentos import H, collect, rig, send, sid, start


def train(client, exp):
    result=client.post(f"/experimentos/{exp['id']}/modelos",headers=H)
    assert result.status_code==201,result.text
    return result.json()


def evaluate(client, exp, comparison=None):
    result=client.post(f"/experimentos/{exp['id']}/avaliar",headers=H,
                       json={'comparacao_id':comparison})
    assert result.status_code==200,result.text
    return result.json()


def test_dados_insuficientes_nao_usa_historico_sem_sessao(rig):
    client,db,clock,exp=rig
    for i in range(105):send(client,clock,i)  # sem sessao: nao pode virar baseline
    result=client.post(f"/experimentos/{exp['id']}/modelos",headers=H)
    assert result.status_code==409 and result.json()['codigo']=='dados_insuficientes'
    report=evaluate(client,exp)
    assert not report['dados_suficientes'] and report['modelos']==[] and report['pontos']==[]
    assert report['status']=='dados_insuficientes'
    with closing(connect(db)) as conn:
        assert conn.execute('select count(*) from modelos_ml').fetchone()[0]==0


def test_baseline_incompleta_recusada(rig):
    client,db,clock,exp=rig
    collect(client,clock,exp,'NORMAL_01',3)
    assert client.post(f"/sessoes/{sid(exp,'NORMAL_01')}/encerrar",headers=H,json={}).status_code==200
    r=client.post(f"/experimentos/{exp['id']}/modelos",headers=H)
    assert r.status_code==409 and r.json()['codigo']=='dados_insuficientes'


def test_treino_apenas_normal01_scaler_sem_vazamento_e_reprodutivel(rig):
    import numpy as np
    client,db,clock,exp=rig
    training_ids=collect(client,clock,exp,'NORMAL_01',100)
    first=train(client,exp)
    validation_ids=collect(client,clock,exp,'NORMAL_02',50,shift=10)
    return_ids=collect(client,clock,exp,'RETORNO_01',50,shift=20)
    report=evaluate(client,exp,first['comparacao_id'])
    second=train(client,exp)
    assert len(first['modelos'])==2
    for original,new in zip(first['modelos'],second['modelos']):
        assert original['ids_treino']==training_ids
        assert set(original['ids_treino']).isdisjoint(validation_ids+return_ids)
        assert original['artefato_sha256']==new['artefato_sha256']
        assert original['dados_sha256']==new['dados_sha256']
    with closing(connect(db)) as conn:
        for model in first['modelos']:
            row=conn.execute('select * from modelos_ml where id=?',(model['id'],)).fetchone()
            pipeline=pickle.loads(row['artefato'])
            rows=conn.execute('select rms,amplitude,pico_fft from medicoes where id in ('+
                              ','.join('?' for _ in training_ids)+') order by id',training_ids).fetchall()
            n=len(model['features'])
            expected=np.mean(np.array([list(r)[:n] for r in rows]),axis=0)
            assert np.allclose(pipeline[0].mean_,expected)
            with pytest.raises(sqlite3.IntegrityError,match='NORMAL_01'):
                conn.execute('insert into ml_treino values(?,?)',(model['id'],validation_ids[0]))
    for model in report['modelos']:
        normal2=next(s for s in model['sessoes'] if s['codigo']=='NORMAL_02')
        returned=next(s for s in model['sessoes'] if s['codigo']=='RETORNO_01')
        assert normal2['papel']==returned['papel']=='avaliacao_separada'
        assert normal2['n']==returned['n']==50
        assert 0<=normal2['taxa_alertas']<=1


def test_scores_persistidos_rastreaveis_idempotentes_e_reinicio(rig):
    client,db,clock,exp=rig
    collect(client,clock,exp,'NORMAL_01',100)
    trained=train(client,exp)
    collect(client,clock,exp,'NORMAL_02',5)
    client.post(f"/sessoes/{sid(exp,'NORMAL_02')}/encerrar",headers=H,json={})
    report=evaluate(client,exp)
    assert len(report['pontos'])==210
    assert not report['dados_suficientes']
    for model in report['modelos']:
        val=next(s for s in model['sessoes'] if s['codigo']=='NORMAL_02')
        assert val['n']==5 and val['taxa_alertas'] is None
    with closing(connect(db)) as conn:
        before=[tuple(r) for r in conn.execute('select * from ml_scores order by modelo_id,medicao_id')]
        assert conn.execute('pragma foreign_key_check').fetchall()==[]
        for point in report['pontos']:
            row=conn.execute('select sessao_id from medicoes_sessoes where medicao_id=?',
                             (point['medicao_id'],)).fetchone()
            assert row[0]==point['sessao_id']
            assert math.isfinite(point['score_decisao']) and point['alerta']==int(point['score_decisao']<0)
        with pytest.raises(sqlite3.IntegrityError,match='imutavel'):
            conn.execute('update ml_scores set score_decisao=0')
    restarted=TestClient(create_app(db_path=db,api_key=H['X-API-Key']))
    after_report=evaluate(restarted,exp,trained['comparacao_id'])
    with closing(connect(db)) as conn:
        assert before==[tuple(r) for r in conn.execute('select * from ml_scores order by modelo_id,medicao_id')]
    assert after_report['pontos']==report['pontos']
    assert restarted.post(f"/experimentos/{exp['id']}/modelos").status_code==401


def test_artefato_alterado_detectado(rig):
    client,db,clock,exp=rig
    collect(client,clock,exp,'NORMAL_01',100)
    trained=train(client,exp)
    evaluate(client,exp)  # Mesmo sem novos pontos, hash divergente deve impedir novo relatorio.
    with closing(connect(db)) as conn:
        conn.execute("update modelos_ml set artefato=? where id=?",(b'nao e pickle',trained['modelos'][0]['id']))
        conn.commit()
    response=client.post(f"/experimentos/{exp['id']}/avaliar",headers=H,json={})
    assert response.status_code==409 and 'Hash' in response.json()['detail']


def test_protocolo_completo_descritivo_com_evento_e_graficos(rig,tmp_path,monkeypatch):
    client,db,clock,exp=rig
    collect(client,clock,exp,'NORMAL_01',100)
    train(client,exp)
    collect(client,clock,exp,'NORMAL_02',50)
    collect(client,clock,exp,'BORRACHA_01',50,shift=.5)
    collect(client,clock,exp,'MADEIRA_01',50,shift=.8)
    assert start(client,exp,'TOQUE_01').status_code==200
    for i in range(10):send(client,clock,i)
    clock.advance(1)
    event=client.post(f"/sessoes/{sid(exp,'TOQUE_01')}/eventos",headers=H,
                       json={'descricao':'FIXTURE: intervalo de perturbacao'}).json()
    for i in range(10):send(client,clock,i,shift=.3)
    clock.advance(1)
    assert client.post(f"/eventos/{event['id']}/encerrar",headers=H).status_code==200
    for i in range(30):send(client,clock,i)
    assert client.post(f"/sessoes/{sid(exp,'TOQUE_01')}/encerrar",headers=H,json={}).status_code==200
    collect(client,clock,exp,'RETORNO_01',50)
    report=evaluate(client,exp)
    assert report['dados_suficientes'] and report['analise_eventos_suficiente']
    assert len(report['pontos'])==700
    for model in report['modelos']:
        assert all(s['dados_suficientes'] and 0<=s['taxa_alertas']<=1 for s in model['sessoes'])
        touch=next(s for s in model['sessoes'] if s['codigo']=='TOQUE_01')
        assert touch['tipo']=='mista_com_eventos'
        assert all(p['n']>=5 and p['taxa_alertas'] is not None
                   for p in touch['eventos'][0]['periodos'].values())
    figures=charts(report)
    assert set(figures)=={'tempo','condicoes','taxas'}
    assert charts(report,'TOQUE_01','durante') and 'taxas' not in charts(report,'TOQUE_01','durante')
    path=tmp_path/'relatorio.html';write_html(report,path)
    content=path.read_text(encoding='utf-8')
    assert 'plotly' in content.lower() and '<script src="https://cdn.plot.ly' not in content
    assert 'FIXTURE' in content and 'Periodos dos eventos' in content
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    json_path=tmp_path/'fixture_report.json'
    json_path.write_text(json.dumps(report),encoding='utf-8')
    monkeypatch.setenv('EXPERIMENT_REPORT_PATH',str(json_path))
    app=AppTest.from_file(str(Path(__file__).resolve().parent.parent/'dashboard/app.py')).run(timeout=30)
    assert not app.exception and app.success
    app.selectbox[0].select('TOQUE_01').run(timeout=30)
    app.selectbox[1].select('durante').run(timeout=30)
    assert not app.exception


@pytest.mark.parametrize('delta,expected',[
    (-61,'fora_da_janela'),(-50,'antes'),(-5,'fronteira_incerta'),(5,'fronteira_incerta'),
    (6,'durante'),(35,'fronteira_incerta'),(46,'depois'),(101,'fora_da_janela'),
])
def test_periodos_tem_faixa_de_incerteza(delta,expected):
    base=datetime(2026,11,10,12,tzinfo=timezone.utc)
    event={'id':1,'descricao':'fixture','inicio':base.isoformat(),'fim':(base+timedelta(seconds=40)).isoformat()}
    assert event_phase((base+timedelta(seconds=delta)).isoformat(),event,[event])==expected


def test_transitorio_curto_sem_amostra_durante_nao_vira_taxa_zero():
    base=datetime(2026,11,10,12,tzinfo=timezone.utc)
    event={'id':1,'descricao':'fixture','inicio':base.isoformat(),'fim':(base+timedelta(seconds=1)).isoformat()}
    points=[{'instante':(base+timedelta(seconds=s)).isoformat(),'alerta':0} for s in [-20,-10,0,1,10,20]]
    result=event_metrics(points,[event])[0]
    assert result['status']=='dados_insuficientes'
    assert result['periodos']['durante']['n']==0 and result['periodos']['durante']['taxa_alertas'] is None


def test_dashboard_sem_dados_e_relatorio_vazio(rig,tmp_path,monkeypatch):
    streamlit=pytest.importorskip('streamlit')
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    client,db,clock,exp=rig
    report=evaluate(client,exp)
    assert charts(report)=={}
    path=tmp_path/'vazio.html';write_html(report,path)
    assert 'Dados insuficientes' in path.read_text(encoding='utf-8')
    monkeypatch.setenv('EXPERIMENT_REPORT_PATH',str(tmp_path/'nao_existe.json'))
    app=AppTest.from_file(str(Path(__file__).resolve().parent.parent/'dashboard/app.py')).run(timeout=30)
    assert not app.exception
    assert app.info
