"""Regressao: dependencias sincronas FastAPI podem trocar de thread."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from backend import database
from backend.main import create_app


def test_request_connection_can_cross_worker_threads(tmp_path):
    path = tmp_path / 'threads.db'
    database.init_db(path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        conn = pool.submit(database.connect, path).result()
    try:
        assert conn.execute('SELECT COUNT(*) FROM medicoes').fetchone()[0] == 0
    finally:
        conn.close()


def test_concurrent_requests_keep_separate_connections(tmp_path):
    app = create_app(db_path=tmp_path / 'concurrent.db', api_key='test-only')
    with TestClient(app) as client:
        def request(i):
            response = client.post('/medicoes', headers={'X-API-Key': 'test-only'}, json={
                'dispositivo': f'fixture-{i}', 'origem': 'real', 'pico_fft': 100,
                'amplitude': 0.1, 'rms': 0.2, 'atrasos': 0,
            })
            assert response.status_code == 201
            return response.json()['id']

        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(request, range(32)))
        assert len(set(ids)) == 32
        response = client.get('/medicoes?limite=100', headers={'X-API-Key': 'test-only'})
        assert response.status_code == 200
        assert len(response.json()) == 32
