"""Contrato fisico e migracao; valores abaixo sao FIXTURES, nao evidencias de hardware."""
import sqlite3
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.database import init_db
from backend.main import create_app

KEY = "chave-de-teste-marco3"
H = {"X-API-Key": KEY}
REAL = dict(dispositivo="esp32-fisico-01", origem="real", pico_fft=162.109375,
            amplitude=0.54, rms=0.45, atrasos=0)
SIM = dict(dispositivo="esp32-wokwi-01", origem="simulacao", rpm=3009.0,
           frequencia_1x=50.15, pico_fft=50.78, amplitude=0.08, cenario=0)
LEGACY_SCHEMA = """
CREATE TABLE medicoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, instante TEXT NOT NULL,
    dispositivo TEXT NOT NULL, rpm REAL NOT NULL, frequencia_1x REAL NOT NULL,
    pico_fft REAL NOT NULL, amplitude REAL NOT NULL, cenario INTEGER NOT NULL,
    origem TEXT NOT NULL);
CREATE INDEX idx_medicoes_instante ON medicoes (instante DESC);
CREATE INDEX idx_medicoes_dispositivo ON medicoes (dispositivo, instante DESC);
"""


@pytest.fixture
def db(tmp_path):
    return tmp_path / "marco3.db"


@pytest.fixture
def client(db):
    return TestClient(create_app(db_path=db, api_key=KEY))


@pytest.mark.parametrize("rotation", [{}, {"rpm": None, "frequencia_1x": None, "cenario": None}])
def test_real_sem_rotacao_persiste_rms_e_atrasos(client, db, rotation):
    r = client.post("/medicoes", json={**REAL, **rotation}, headers=H)
    assert r.status_code == 201
    id_ = r.json()["id"]
    out = client.get(f"/medicoes/{id_}", headers=H).json()
    assert all(out[name] is None for name in ("rpm", "frequencia_1x", "cenario"))
    assert all(out[name] == value for name, value in REAL.items())
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT origem,rpm,frequencia_1x,cenario,rms,atrasos FROM medicoes").fetchone()
    assert row == ("real", None, None, None, 0.45, 0)
    restarted = TestClient(create_app(db_path=db, api_key=KEY))
    assert restarted.get(f"/medicoes/{id_}", headers=H).json() == out


def test_origens_coexistem_e_consulta_por_dispositivo(client):
    assert client.post("/medicoes", json=SIM, headers=H).status_code == 201
    assert client.post("/medicoes", json=REAL, headers=H).status_code == 201
    both = client.get("/medicoes", headers=H).json()
    assert {m["origem"] for m in both} == {"real", "simulacao"}
    only_real = client.get("/medicoes?dispositivo=esp32-fisico-01", headers=H).json()
    assert len(only_real) == 1 and only_real[0]["origem"] == "real"
    only_sim = client.get("/medicoes?dispositivo=esp32-wokwi-01", headers=H).json()
    assert len(only_sim) == 1 and only_sim[0]["rms"] is None


@pytest.mark.parametrize("header", [{}, {"X-API-Key": "errada"}])
def test_autenticacao_fisico(client, db, header):
    assert client.post("/medicoes", json=REAL, headers=header).status_code == 401
    assert client.get("/medicoes?dispositivo=esp32-fisico-01", headers=header).status_code == 401
    assert client.get("/medicoes/1", headers=header).status_code == 401
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM medicoes").fetchone()[0] == 0


@pytest.mark.parametrize("field,value", [
    ("rms", -0.01), ("rms", "abc"), ("rms", 1001), ("rms", "NaN"), ("rms", "Infinity"),
    ("atrasos", -1), ("atrasos", 257), ("atrasos", 1.5), ("atrasos", True), ("atrasos", "2"),
    ("rpm", -1), ("rpm", 20001), ("rpm", "inf"),
    ("frequencia_1x", -1), ("frequencia_1x", "nan"),
    ("pico_fft", -1), ("pico_fft", "nan"), ("pico_fft", "inf"),
    ("amplitude", -1), ("amplitude", "NaN"), ("amplitude", "Infinity"),
    ("cenario", 3), ("origem", "fisico"), ("nao_previsto", 1),
])
def test_numeros_e_contrato_invalidos(client, field, value):
    assert client.post("/medicoes", json={**REAL, field: value}, headers=H).status_code == 422


@pytest.mark.parametrize("field", ["pico_fft", "amplitude", "origem", "dispositivo"])
def test_fisico_exige_campos_base(client, field):
    data = dict(REAL)
    del data[field]
    assert client.post("/medicoes", json=data, headers=H).status_code == 422


@pytest.mark.parametrize("field", ["rpm", "frequencia_1x", "cenario"])
def test_simulacao_mantem_campos_obrigatorios(client, field):
    data = dict(SIM)
    del data[field]
    assert client.post("/medicoes", json=data, headers=H).status_code == 422
    assert client.post("/medicoes", json={**SIM, field: None}, headers=H).status_code == 422


def create_legacy(db):
    with sqlite3.connect(db) as conn:
        conn.executescript(LEGACY_SCHEMA)
        conn.execute("INSERT INTO medicoes VALUES (7,?,?,?,?,?,?,?,?)",
                     ("2026-10-26T23:09:45.133+00:00", SIM["dispositivo"], SIM["rpm"],
                      SIM["frequencia_1x"], SIM["pico_fft"], SIM["amplitude"], 0, "simulacao"))
        conn.execute("INSERT INTO medicoes SELECT 99,instante,dispositivo,rpm,frequencia_1x,"
                     "pico_fft,amplitude,cenario,origem FROM medicoes WHERE id=7")
        conn.execute("DELETE FROM medicoes WHERE id=99")
        conn.execute("CREATE INDEX idx_extra_origem ON medicoes(origem)")
        return conn.execute("SELECT * FROM medicoes").fetchall()


def test_migracao_preserva_dados_indices_sequencia_backup_e_reinicio(db):
    before = create_legacy(db)
    client = TestClient(create_app(db_path=db, api_key=KEY))
    old = client.get("/medicoes/7", headers=H).json()
    assert old["rpm"] == SIM["rpm"] and old["rms"] is None and old["atrasos"] is None
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT id,instante,dispositivo,rpm,frequencia_1x,pico_fft,amplitude,"
                            "cenario,origem FROM medicoes").fetchall() == before
        indexes = {r[1] for r in conn.execute("PRAGMA index_list(medicoes)")}
        assert {"idx_medicoes_instante", "idx_medicoes_dispositivo", "idx_extra_origem"} <= indexes
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    result = client.post("/medicoes", json=REAL, headers=H)
    assert result.status_code == 201 and result.json()["id"] == 100
    backups = list(db.parent.glob(db.name + ".pre-marco3-*.bak"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("SELECT * FROM medicoes").fetchall() == before
        assert "rms" not in {r[1] for r in conn.execute("PRAGMA table_info(medicoes)")}
    init_db(db)
    assert list(db.parent.glob(db.name + ".pre-marco3-*.bak")) == backups
    restarted = TestClient(create_app(db_path=db, api_key=KEY))
    assert len(restarted.get("/medicoes", headers=H).json()) == 2


def test_migracao_recusa_colunas_desconhecidas_sem_perda(db):
    before = create_legacy(db)
    with sqlite3.connect(db) as conn:
        conn.execute("ALTER TABLE medicoes ADD COLUMN anotacao TEXT")
        conn.execute("UPDATE medicoes SET anotacao='preservar'")
    with pytest.raises(RuntimeError, match="colunas desconhecidas"):
        init_db(db)
    with sqlite3.connect(db) as conn:
        after = conn.execute("SELECT * FROM medicoes").fetchall()
        assert after == [(*before[0], "preservar")]
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='medicoes_marco3'").fetchone() is None


def test_migracao_rollback_se_copia_falhar(db):
    before = create_legacy(db)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE medicoes_marco3 (bloqueio TEXT)")
    with pytest.raises(sqlite3.OperationalError):
        init_db(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT * FROM medicoes").fetchall() == before
        assert conn.execute("SELECT seq FROM sqlite_sequence WHERE name='medicoes'").fetchone()[0] == 99


def test_scripts_consulta_antes_e_depois_da_migracao(db):
    create_legacy(db)
    root = Path(__file__).resolve().parent.parent
    def run(script, device):
        return subprocess.run([sys.executable, str(root / "scripts" / script), "--db", str(db),
                               "-d", device], capture_output=True, text=True, check=True).stdout
    assert "simulacao" in run("print_banco.py", "esp32-wokwi-01")
    client = TestClient(create_app(db_path=db, api_key=KEY))
    client.post("/medicoes", json=REAL, headers=H)
    for script in ("consultar_dados.py", "print_banco.py"):
        output = run(script, "esp32-fisico-01")
        assert "rms" in output and "atrasos" in output and "real" in output and "0.45" in output


@pytest.mark.parametrize("key", ["", "   ", "troque-por-uma-chave-longa-e-aleatoria"])
def test_iniciador_lan_recusa_chave_insegura(db, key):
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "API_KEY": key, "DB_PATH": str(db)}
    result = subprocess.run([sys.executable, str(root / "scripts/iniciar_api_local.py")],
                            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0 and "Configure API_KEY" in result.stderr
    assert not db.exists()


def test_migracao_preserva_trigger_e_colunas_opcionais_existentes(db):
    create_legacy(db)
    with sqlite3.connect(db) as conn:
        conn.execute("ALTER TABLE medicoes ADD COLUMN rms REAL")
        conn.execute("UPDATE medicoes SET rms=0.05 WHERE id=7")
        conn.execute("CREATE TABLE auditoria (medicao_id INTEGER)")
        conn.execute("CREATE TRIGGER log_insert AFTER INSERT ON medicoes BEGIN "
                     "INSERT INTO auditoria(medicao_id) VALUES (new.id); END")
    client = TestClient(create_app(db_path=db, api_key=KEY))
    assert client.get("/medicoes/7", headers=H).json()["rms"] == 0.05
    result = client.post("/medicoes", json=REAL, headers=H)
    assert result.status_code == 201
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT medicao_id FROM auditoria").fetchall() == [(result.json()["id"],)]
