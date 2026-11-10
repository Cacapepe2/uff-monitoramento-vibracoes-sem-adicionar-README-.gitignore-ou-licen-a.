"""Testes isolados: nunca enviam fixtures para Supabase real."""
import base64
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from cloud_sync.queue import Queue
from cloud_sync.transport import Supabase,safe_config
from cloud_sync.public_data import FIELDS,document,read_objects,validate_document
from dashboard.public_view import bundled,measurement_state,replay_window,unpack
from scripts.gerar_qrcode import validate_url
from scripts.sincronizar_supabase import cycle
from test_experimentos import rig,send,start,H


def item(value=1):return ('measurement','1',{'value':value})


def test_incremental_ack_reinicio_e_update(tmp_path):
    path=tmp_path/'out.db';q=Queue(path);source=q.source_id
    assert q.scan([item()])==1
    assert q.scan([item()])==0
    batch=q.claim(now=10);q.finish(batch,True,now=11)
    assert q.status()['pending']==0
    q=Queue(path);assert q.source_id==source
    assert q.scan([item(2)])==1
    assert q.claim(now=12)[0]['revision']==2
    with pytest.raises(ValueError):Queue(path,str(uuid4()))


def test_perda_ack_reenvio_mesma_identidade_e_backoff(tmp_path):
    q=Queue(tmp_path/'out.db');q.scan([item()]);first=q.claim(now=10)
    q.finish(first,False,now=10)
    assert not q.claim(now=14)
    second=q.claim(now=15)
    assert [(r['entity_id'],r['revision'],r['hash']) for r in first]==[(r['entity_id'],r['revision'],r['hash']) for r in second]
    q.finish(second,True,now=16);assert q.status()['pending']==0


def test_lease_concorrencia_expira_e_ack_antigo_nao_apaga_novo(tmp_path):
    q=Queue(tmp_path/'out.db');q.scan([item()]);first=q.claim(now=0)
    assert not q.claim(now=1)
    second=q.claim(now=121)
    q.finish(first,True,now=122);assert q.status()['pending']==1
    q.scan([item(2)])
    q.finish(second,True,now=123)
    assert q.status()['pending']==1
    assert q.claim(now=124)[0]['revision']==2


def test_projecao_publica_sem_texto_livre_pickle_ou_simulacao(rig):
    client,db,clock,exp=rig
    send(client,clock,origem='simulacao',rpm=3000,frequencia_1x=50,cenario=0)
    start(client,exp,'NORMAL_01');mid=send(client,clock)['id']
    before=db.read_bytes()
    objects=read_objects(db)
    assert db.read_bytes()==before
    assert [p['id'] for k,i,p in objects if k=='measurement']==[mid]
    assert any(k=='membership' for k,i,p in objects)
    for kind,eid,payload in objects:
        assert set(payload)==set(FIELDS[kind])
        assert not {'observacoes','condicao_observada','artefato','writer_uid'}&set(payload)
    validate_document(document(objects,str(uuid4()),'2026-11-10T00:00:00+00:00'))


def test_falha_cloud_nao_interrompe_ingestao_e_fila_permanece(rig,tmp_path):
    client,db,clock,exp=rig
    send(client,clock)
    class Offline:
        token='fake';expires=10**12
        def send(self,source,batch):raise TimeoutError('fixture de rede offline')
    q=Queue(tmp_path/'queue.db')
    result=cycle(q,db,Offline())
    assert result['failed']>0 and result['pending']>0 and result['last_success_at'] is None
    assert send(client,clock)['id']>1


def test_novo_registro_entra_incrementalmente_sem_reenviar_antigos(rig,tmp_path):
    client,db,clock,exp=rig
    send(client,clock);q=Queue(tmp_path/'queue.db')
    objects=read_objects(db);q.scan(objects)
    batch=q.claim(now=10);q.finish(batch,True,now=11)
    assert q.scan(read_objects(db))==0
    second=send(client,clock)['id']
    assert q.scan(read_objects(db))==1
    assert q.claim(now=12)[0]['entity_id']==str(second)


@pytest.mark.parametrize('url,key',[
    ('http://x.supabase.co','sb_publishable_fake'),('https://localhost','sb_publishable_fake'),
    ('https://x.supabase.co.evil.test','sb_publishable_fake'),('https://x.supabase.co','sb_secret_private'),
    ('https://user:password@x.supabase.co','sb_publishable_fake'),('https://x.supabase.co?key=private','sb_publishable_fake'),
    ('https://x.supabase.co','eyJ.'+base64.urlsafe_b64encode(b'{"role":"service_role"}').decode().rstrip('=')+'.x'),
])
def test_nao_aceita_destino_inseguro_ou_chave_privilegiada(url,key):
    with pytest.raises(ValueError):safe_config(url,key)


def test_leitura_anonima_nao_usa_senha_e_ack_precisa_confirmacao():
    class Response:
        status_code=200
        def json(self):return []
    class Fake:
        calls=[]
        def get(self,url,**kw):self.calls.append(kw);return Response()
        def post(self,url,**kw):return Response()
    session=Fake();api=Supabase('https://example.supabase.co','sb_publishable_test',session)
    assert api.read(str(uuid4()))==[]
    assert 'Authorization' not in session.calls[0]['headers']
    with pytest.raises(RuntimeError):api.send(str(uuid4()),[])
    api.token='test-token';api.expires=10**12
    with pytest.raises(RuntimeError,match='nao confirmado'):api.send(str(uuid4()),[])


def test_replay_publicado_rastreavel_e_timestamps_preservados():
    data=bundled(Path(__file__).resolve().parent.parent/'dashboard/data/replay.json')
    full=unpack(data);partial,total=replay_window(data,2)
    assert data['historical'] is True and total==355
    assert len(partial['measurement'])==2
    assert partial['measurement']==full['measurement'][:2]
    mids={r['id'] for r in partial['measurement']}
    assert all(r['medicao_id'] in mids for r in partial['score'])
    assert len(full['score'])==710 and len(full['session'])==6


def test_estado_da_medicao_distingue_relogio_antigo_recente():
    now=datetime(2026,11,10,tzinfo=timezone.utc)
    assert measurement_state([])[0]=='Sem medições'
    assert measurement_state([{'instante':now.isoformat()}],now)[0]=='Medição recente'
    assert measurement_state([{'instante':(now-timedelta(minutes=2)).isoformat()}],now)[0]=='Sem medição recente'
    assert measurement_state([{'instante':(now+timedelta(minutes=2)).isoformat()}],now)[0]=='Relógio inconsistente'


@pytest.mark.parametrize('url',['http://fake.streamlit.app','https://localhost','https://fake.streamlit.app?key=secret'])
def test_qr_nao_usa_url_insegura_ou_credenciais(url):
    with pytest.raises(ValueError):validate_url(url)
