"""Rotas autenticadas; inferencia nao participa da janela de aquisicao/POST."""
import json

from fastapi import APIRouter, Depends, Query

from . import experiments as service
from .experimental_schemas import EvaluationIn, EventIn, ExperimentIn, SessionEnd, SessionStart


def build_router(get_conn, auth):
    router = APIRouter(dependencies=[Depends(auth)], tags=['Experimentos'])

    @router.post('/experimentos', status_code=201)
    def create(body: ExperimentIn, conn=Depends(get_conn)):
        return service.create_experiment(conn, body.nome, body.dispositivo, body.observacoes)

    @router.get('/experimentos')
    def list_experiments(conn=Depends(get_conn)):
        return [dict(r) for r in conn.execute('SELECT * FROM experimentos ORDER BY criado_em DESC,id')]

    @router.get('/experimentos/{eid}')
    def detail(eid: str, conn=Depends(get_conn)):
        return service.experiment_summary(conn, eid)

    @router.get('/sessoes/{sid}')
    def session(sid: int, conn=Depends(get_conn)):
        data = service.session_summary(conn, sid)
        data['auditoria'] = [{**dict(r), 'detalhes': json.loads(r['detalhes'])} for r in conn.execute(
            'SELECT * FROM auditoria_sessoes WHERE sessao_id=? ORDER BY id', (sid,))]
        return data

    @router.post('/sessoes/{sid}/iniciar')
    def start(sid: int, body: SessionStart, conn=Depends(get_conn)):
        return service.start_session(conn, sid, body.condicao, body.observacoes, body.espera_estabilizacao_s)

    @router.post('/sessoes/{sid}/encerrar')
    def end(sid: int, body: SessionEnd, conn=Depends(get_conn)):
        return service.end_session(conn, sid, body.observacoes)

    @router.get('/sessoes/{sid}/medicoes')
    def measurements(sid: int, limite: int = Query(1000, ge=1, le=1000), conn=Depends(get_conn)):
        return service.session_measurements(conn, sid)[:limite]

    @router.get('/medicoes/{mid}/sessao')
    def association(mid: int, conn=Depends(get_conn)):
        if not conn.execute('SELECT 1 FROM medicoes WHERE id=?', (mid,)).fetchone():
            raise service.ProtocolError('Medicao nao encontrada', 404)
        row = conn.execute('SELECT a.*,s.codigo,s.experimento_id FROM medicoes_sessoes a '
            'JOIN sessoes_experimentais s ON s.id=a.sessao_id WHERE a.medicao_id=?', (mid,)).fetchone()
        return dict(row) if row else None

    @router.post('/sessoes/{sid}/eventos', status_code=201)
    def begin_event(sid: int, body: EventIn, conn=Depends(get_conn)):
        return service.begin_event(conn, sid, body.descricao, body.observacoes)

    @router.post('/eventos/{event_id}/encerrar')
    def end_event(event_id: int, conn=Depends(get_conn)):
        return service.end_event(conn, event_id)

    @router.post('/experimentos/{eid}/modelos', status_code=201)
    def train(eid: str, conn=Depends(get_conn)):
        from analytics.isolation import train_comparison
        return train_comparison(conn, eid)

    @router.get('/experimentos/{eid}/modelos')
    def models(eid: str, conn=Depends(get_conn)):
        from analytics.isolation import list_models
        return list_models(conn, eid)

    @router.post('/experimentos/{eid}/avaliar')
    def evaluate(eid: str, body: EvaluationIn, conn=Depends(get_conn)):
        from analytics.isolation import evaluate
        return evaluate(conn, eid, body.comparacao_id)

    return router
