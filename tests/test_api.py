import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app

KEY = "chave-de-teste"
H = {"X-API-Key": KEY}
BASE = dict(dispositivo="esp32-wokwi-01", rpm=3009.0, frequencia_1x=50.15,
            pico_fft=50.78, amplitude=0.08, cenario=0, origem="simulacao")


@pytest.fixture
def db(tmp_path):
    return tmp_path / "teste.db"


@pytest.fixture
def client(db):
    return TestClient(create_app(db_path=db, api_key=KEY))


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_banco_criado(db, client):
    assert db.exists()
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT name FROM sqlite_master WHERE name='medicoes'").fetchone()


def test_insercao_201_e_consulta(client):
    r = client.post("/medicoes", json=BASE, headers=H)
    assert r.status_code == 201
    id_ = r.json()["id"]
    g = client.get(f"/medicoes/{id_}", headers=H)
    assert g.status_code == 200
    assert g.json()["rpm"] == 3009.0 and g.json()["instante"].endswith("+00:00")


def test_persistencia_apos_reinicio(db):
    c1 = TestClient(create_app(db_path=db, api_key=KEY))
    id_ = c1.post("/medicoes", json=BASE, headers=H).json()["id"]
    c2 = TestClient(create_app(db_path=db, api_key=KEY))  # "reinicia" a API
    assert c2.get(f"/medicoes/{id_}", headers=H).status_code == 200


def test_inexistente_404(client):
    assert client.get("/medicoes/9999", headers=H).status_code == 404


@pytest.mark.parametrize("campo,valor", [
    ("rpm", -1), ("rpm", "abc"), ("cenario", 5), ("origem", "outra"),
    ("dispositivo", ""), ("amplitude", -0.1)])
def test_campos_invalidos_422(client, campo, valor):
    r = client.post("/medicoes", json={**BASE, campo: valor}, headers=H)
    assert r.status_code == 422


def test_campo_ausente_422(client):
    b = dict(BASE)
    del b["rpm"]
    assert client.post("/medicoes", json=b, headers=H).status_code == 422


def test_auth(client):
    assert client.post("/medicoes", json=BASE).status_code == 401
    assert client.post("/medicoes", json=BASE, headers={"X-API-Key": "errada"}).status_code == 401
    assert client.get("/medicoes").status_code == 401


def test_ordenacao_limite_filtro(client):
    for i in range(5):
        client.post("/medicoes", json={**BASE, "rpm": 3000 + i,
                                       "dispositivo": "a" if i % 2 else "b"}, headers=H)
    r = client.get("/medicoes?limite=3", headers=H).json()
    assert [m["rpm"] for m in r] == [3004, 3003, 3002]
    assert len(client.get("/medicoes?limite=1", headers=H).json()) == 1
    assert client.get("/medicoes?limite=0", headers=H).status_code == 422
    assert all(m["dispositivo"] == "a"
               for m in client.get("/medicoes?dispositivo=a", headers=H).json())
