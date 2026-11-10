"""Renderizacao e atualizacao do painel com replay fisico ja preservado."""
import pytest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from cloud_sync.public_data import ML_WARNING
import streamlit as st


@pytest.fixture(autouse=True)
def ambiente_painel_isolado(monkeypatch):
    # Credenciais locais carregadas por outros testes nao devem ativar rede real.
    monkeypatch.setattr(st, 'secrets', {})
    for name in ['SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY', 'CLOUD_SOURCE_ID']:
        monkeypatch.delenv(name, raising=False)
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


def app():
    return AppTest.from_file(Path(__file__).resolve().parent.parent/'dashboard/app_publico.py',default_timeout=30).run()


def test_publico_renderiza_aviso_e_replay_sem_segredos(monkeypatch):
    for name in ['SUPABASE_URL','SUPABASE_PUBLISHABLE_KEY','CLOUD_SOURCE_ID']:monkeypatch.delenv(name,raising=False)
    at=app();assert not at.exception
    assert at.title[0].value=='Atividade de Extensão de Sistema de Computação'
    assert not any(ML_WARNING==v.value for v in at.warning)
    assert any('REPLAY DE DADOS REAIS HISTÓRICOS' in v.value for v in at.info)
    assert len(at.metric)==3


@pytest.mark.parametrize('page',['Histórico de vibração','Sessões experimentais','Machine Learning experimental','Como funciona','Limitações e próximos passos'])
def test_paginas_sem_excecao(page):
    at=app();at.sidebar.radio[1].set_value(page).run();assert not at.exception
    if page=='Machine Learning experimental':
        assert any(ML_WARNING==v.value for v in at.warning)


def test_replay_atualiza_prefixo_sem_alterar_tempo_real():
    at=app();at.sidebar.toggle[0].set_value(True).run()
    cursor=at.session_state['replay_cursor']
    at.run()
    assert at.session_state['replay_cursor']>cursor
    assert not at.exception


def test_cloud_sem_configuracao_nao_finge_conexao(monkeypatch):
    for name in ['SUPABASE_URL','SUPABASE_PUBLISHABLE_KEY','CLOUD_SOURCE_ID']:monkeypatch.delenv(name,raising=False)
    at=app();at.sidebar.radio[0].set_value('Nuvem · Supabase').run()
    assert not at.exception
    assert any('Nuvem não configurada' in v.value for v in at.info)


def test_nova_consulta_cloud_atualiza_dados_e_falha_nao_vira_replay(monkeypatch):
    import copy
    import cloud_sync.transport as transport
    from dashboard.public_view import bundled
    root=Path(__file__).resolve().parent.parent
    dataset=copy.deepcopy(bundled(root/'dashboard/data/replay.json'))
    class FakeCloud:
        offline=False
        def __init__(self,*args):pass
        def read(self,source):
            if FakeCloud.offline:raise RuntimeError('fixture: sem rede')
            return copy.deepcopy(dataset['objects'])
    monkeypatch.setattr(transport,'Supabase',FakeCloud)
    monkeypatch.setenv('SUPABASE_URL','https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY','sb_publishable_fixture')
    monkeypatch.setenv('CLOUD_SOURCE_ID',dataset['source_id'])
    st.cache_data.clear()
    at=app();assert not at.exception
    assert not at.success
    previous=at.metric[0].value
    last=max((r for r in dataset['objects'] if r['kind']=='measurement'),key=lambda x:x['payload']['id'])
    last['payload']['rms']=123.456 # fixture isolada, nao escreve o replay real
    st.cache_data.clear();at.run()
    assert not at.exception and at.metric[0].value!=previous
    FakeCloud.offline=True;st.cache_data.clear();at.run()
    assert any('Consulta à nuvem indisponível' in v.value for v in at.error)
    assert any('cache' in v.value for v in at.warning)
    assert not any('REPLAY DE DADOS REAIS HISTÓRICOS' in v.value for v in at.info)
    assert not at.exception
    st.cache_data.clear()
