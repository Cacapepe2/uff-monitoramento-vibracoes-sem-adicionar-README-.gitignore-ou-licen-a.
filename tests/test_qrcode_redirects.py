"""Verificacao HTTPS do QR com bootstrap publico e redirects restritos."""
import pytest

from scripts.gerar_qrcode import verify_public_url


def session(monkeypatch, responses):
    calls=[]

    class FakeSession:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url,**kwargs):
            calls.append(url)
            assert kwargs['allow_redirects'] is False
            return responses.pop(0)

    import requests
    monkeypatch.setattr(requests,'Session',FakeSession)
    return calls


def response(code, location=None):
    class Response:
        status_code=code
        headers={} if location is None else {'Location':location}
    return Response()


def test_bootstrap_oficial_retorna_ao_app_sem_login(monkeypatch):
    url='https://fixture.streamlit.app/'
    calls=session(monkeypatch,[response(303,'https://share.streamlit.io/-/auth/app'),
                               response(303,url),response(200)])
    verify_public_url(url)
    assert calls==[url,'https://share.streamlit.io/-/auth/app',url]


@pytest.mark.parametrize('location',['https://example.com/',
    'http://fixture.streamlit.app/','https://user:pass@fixture.streamlit.app/'])
def test_nao_segue_redirecionamento_inseguro(monkeypatch,location):
    calls=session(monkeypatch,[response(303,location)])
    with pytest.raises(ValueError):verify_public_url('https://fixture.streamlit.app/')
    assert len(calls)==1


def test_pagina_central_nao_comprova_publicacao(monkeypatch):
    session(monkeypatch,[response(303,'https://share.streamlit.io/'),response(200)])
    with pytest.raises(ValueError):verify_public_url('https://fixture.streamlit.app/')
