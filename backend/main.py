import hmac
import logging
import os
import sqlite3

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query

from . import database
from . import experiments
from .models import INSERT
from .schemas import MedicaoCriada, MedicaoIn, MedicaoOut

log = logging.getLogger("uvicorn.error")
COLS = "id, instante, dispositivo, rpm, frequencia_1x, pico_fft, amplitude, cenario, origem, rms, atrasos"


def create_app(db_path=None, api_key=None) -> FastAPI:
    """Cria a aplicacao. Os parametros permitem isolar banco e chave nos testes."""
    load_dotenv(database.ROOT / ".env")
    path = database.resolve_db_path(db_path)
    key = api_key if api_key is not None else os.getenv("API_KEY", "")
    database.init_db(path)
    if not key:
        log.warning("API_KEY nao definida: autenticacao DESLIGADA. Nao exponha a API (tunel) assim.")

    app = FastAPI(title="Monitoramento de Ventilador", version="0.1.0")

    def get_conn():
        conn = database.connect(path)
        try:
            yield conn
        finally:
            conn.close()

    def auth(x_api_key: str | None = Header(default=None)):
        if key and not (x_api_key and hmac.compare_digest(x_api_key, key)):
            raise HTTPException(status_code=401, detail="Chave de API ausente ou invalida")

    @app.get("/health")
    def health(conn: sqlite3.Connection = Depends(get_conn)):
        try:
            conn.execute("SELECT 1")
            db = "ok"
        except sqlite3.Error:
            db = "erro"
        return {"status": "ok" if db == "ok" else "degradado", "banco": db, "auth": bool(key)}

    @app.post("/medicoes", status_code=201, response_model=MedicaoCriada, response_model_exclude_none=True,
              dependencies=[Depends(auth)])
    def criar(m: MedicaoIn, conn: sqlite3.Connection = Depends(get_conn)):
        try:
            conn.execute('BEGIN IMMEDIATE')
            instante = experiments.iso(experiments.utc_now())
            cur = conn.execute(INSERT, (instante, m.dispositivo, m.rpm, m.frequencia_1x,
                                        m.pico_fft, m.amplitude, m.cenario, m.origem,
                                        m.rms, m.atrasos))
            mid = cur.lastrowid
            sid = experiments.associate_received(conn, mid, m.model_dump(), instante)
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            log.error("Falha ao gravar: %s", e)
            raise HTTPException(status_code=500, detail="Erro ao gravar no banco")
        return {"id": mid, "instante": instante, "sessao_id": sid}

    @app.get("/medicoes", response_model=list[MedicaoOut], dependencies=[Depends(auth)])
    def listar(limite: int = Query(50, ge=1, le=1000),
               dispositivo: str | None = None,
               conn: sqlite3.Connection = Depends(get_conn)):
        sql, args = f"SELECT {COLS} FROM medicoes", []
        if dispositivo:
            sql += " WHERE dispositivo = ?"
            args.append(dispositivo)
        sql += " ORDER BY instante DESC, id DESC LIMIT ?"
        args.append(limite)
        return [dict(r) for r in conn.execute(sql, args)]

    @app.get("/medicoes/{id}", response_model=MedicaoOut, dependencies=[Depends(auth)])
    def obter(id: int, conn: sqlite3.Connection = Depends(get_conn)):
        row = conn.execute(f"SELECT {COLS} FROM medicoes WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Medicao nao encontrada")
        return dict(row)

    from .experimental_api import build_router
    app.include_router(build_router(get_conn, auth))

    from fastapi.responses import JSONResponse

    @app.exception_handler(experiments.ProtocolError)
    async def protocol_error(request, exc):
        return JSONResponse(status_code=exc.status,
                            content={'detail': exc.message, 'codigo': exc.code})

    return app


# Execucao: uvicorn backend.main:create_app --factory
# (sem instancia global, para que importar o modulo nao crie o banco real)
