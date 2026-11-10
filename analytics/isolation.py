"""Isolation Forest com baseline imutavel e avaliacao separada por sessao."""
import hashlib
import json
import pickle
import platform
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from backend import experiments as protocol

FEATURE_SETS = {'rms_amplitude': ['rms', 'amplitude'],
                'rms_amplitude_frequencia': ['rms', 'amplitude', 'pico_fft']}
PARAMETERS = dict(n_estimators=200, max_samples='auto', contamination='auto',
                  random_state=42, n_jobs=1)
EVENT_WINDOW_S = 60
EVENT_GUARD_S = 5
MIN_PERIOD_SAMPLES = 5


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def model_metadata(conn, row):
    data = dict(row)
    data.pop('artefato')
    for key in ('features', 'parametros', 'ambiente'):
        data[key] = json.loads(data.pop(key+'_json'))
    data['ids_treino'] = [r[0] for r in conn.execute(
        'SELECT medicao_id FROM ml_treino WHERE modelo_id=? ORDER BY medicao_id', (data['id'],))]
    return data


def list_models(conn, eid):
    protocol.get_experiment(conn, eid)
    return [model_metadata(conn, r) for r in conn.execute(
        'SELECT * FROM modelos_ml WHERE experimento_id=? ORDER BY criado_em,variante,id', (eid,)).fetchall()]


def train_comparison(conn, eid):
    # Dependencias ML nao sao necessarias para a ingestao ESP32/FastAPI.
    try:
        import numpy as np
        import sklearn
    except ImportError as exc:
        raise protocol.ProtocolError('Instale requirements-ml.txt para treinar modelos',
                                     503, 'dependencias_ml_ausentes') from exc
    from sklearn.ensemble import IsolationForest
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    exp = protocol.experiment_summary(conn, eid)
    baseline = next(s for s in exp['sessoes'] if s['codigo'] == 'NORMAL_01')
    if not baseline['dados_suficientes']:
        raise protocol.ProtocolError(
            f"Dados insuficientes: NORMAL_01 precisa estar encerrada com 100 registros elegiveis; "
            f"atual={baseline['registros_elegiveis']}, estado={baseline['estado']}",
            code='dados_insuficientes')
    rows = protocol.session_measurements(conn, baseline['id'], eligible_only=True)
    if len(rows) != 100:
        raise protocol.ProtocolError('Baseline deve conter exatamente 100 registros elegiveis',
                                     code='dados_insuficientes')
    if not np.any(np.ptp([[r['rms'], r['amplitude']] for r in rows], axis=0) > 0):
        raise protocol.ProtocolError('RMS e amplitude constantes: revisar aquisicao antes de treinar',
                                     code='dados_insuficientes')
    env = {'python': platform.python_version(), 'numpy': np.__version__,
           'sklearn': sklearn.__version__, 'protocolo': protocol.PROTOCOL_VERSION,
           'source_sha256': {name: hashlib.sha256((Path(__file__).resolve().parent.parent/name).read_bytes()).hexdigest()
             for name in ('analytics/isolation.py', 'backend/experiments.py', 'backend/experiment_schema.py')}}
    training_snapshot = {'sessao': baseline, 'medicoes': rows}
    digest = hashlib.sha256(canonical(training_snapshot).encode('utf-8')).hexdigest()
    comparison_id, instant = str(uuid4()), protocol.iso(protocol.utc_now())
    pending = []
    for variant, features in FEATURE_SETS.items():
        x = np.array([[r[f] for f in features] for r in rows], dtype=float)
        pipeline = make_pipeline(StandardScaler(), IsolationForest(**PARAMETERS))
        pipeline.fit(x)  # SOMENTE NORMAL_01: sem fit, scaler ou ajuste em outras sessoes.
        artifact = pickle.dumps(pipeline, protocol=5)
        params = {**PARAMETERS, 'scaler': 'StandardScaler fit somente NORMAL_01',
                  'offset': float(pipeline[-1].offset_), 'criterio_alerta': 'score_decisao < 0'}
        pending.append((str(uuid4()), variant, features, params, artifact))
    with conn:
        for mid, variant, features, params, artifact in pending:
            conn.execute('INSERT INTO modelos_ml VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (mid, comparison_id, eid, baseline['id'], variant, canonical(features), canonical(params),
                 canonical(env), digest, hashlib.sha256(artifact).hexdigest(), artifact, instant))
            conn.executemany('INSERT INTO ml_treino VALUES(?,?)', [(mid, r['id']) for r in rows])
    return {'comparacao_id': comparison_id, 'modelos': [m for m in list_models(conn, eid)
                                                      if m['comparacao_id'] == comparison_id]}


def load_model(row):
    import sklearn
    if json.loads(row['ambiente_json'])['sklearn'] != sklearn.__version__:
        raise protocol.ProtocolError('Versao sklearn diferente da versao do modelo; use ambiente registrado')
    artifact = row['artefato']
    if hashlib.sha256(artifact).hexdigest() != row['artefato_sha256']:
        raise protocol.ProtocolError('Hash do artefato divergente; avaliacao recusada')
    # Apenas artefatos gerados por esta aplicacao em banco LOCAL confiavel.
    # Nao ha endpoint de upload de pickle; o dashboard aceita somente relatorio JSON.
    return pickle.loads(artifact)


def score_closed_sessions(conn, models, sessions):
    import numpy as np
    for model in models:
        # Validar tambem quando todos os scores ja estao persistidos.
        pipeline = load_model(model)
        features = json.loads(model['features_json'])
        pending = []
        for session in sessions:
            if session['estado'] != 'encerrada':
                continue
            existing = {r[0] for r in conn.execute('SELECT medicao_id FROM ml_scores WHERE modelo_id=? '
                'AND sessao_id=?', (model['id'], session['id']))}
            pending.extend((session, r) for r in protocol.session_measurements(conn, session['id'], True)
                           if r['id'] not in existing)
        if not pending:
            continue
        x = np.array([[r[f] for f in features] for _, r in pending], dtype=float)
        raw = pipeline.score_samples(x)
        decision = pipeline.decision_function(x)
        instant = protocol.iso(protocol.utc_now())
        with conn:
            conn.executemany('INSERT OR IGNORE INTO ml_scores VALUES(?,?,?,?,?,?,?,?)', [
                (model['id'], r['id'], s['id'], 'treinamento' if s['codigo']=='NORMAL_01' else 'avaliacao',
                 float(a), float(b), int(b < 0), instant)
                for (s, r), a, b in zip(pending, raw, decision)])


def event_phase(instant, event, all_events):
    """Fases aproximadas POR RECEPCAO, com fronteiras excluidas por incerteza."""
    t = datetime.fromisoformat(instant)
    start, end = datetime.fromisoformat(event['inicio']), datetime.fromisoformat(event['fim'])
    guard, window = timedelta(seconds=EVENT_GUARD_S), timedelta(seconds=EVENT_WINDOW_S)
    if abs((t-start).total_seconds()) <= EVENT_GUARD_S or abs((t-end).total_seconds()) <= EVENT_GUARD_S:
        return 'fronteira_incerta'
    before, after = start-window, end+window
    for other in all_events:
        if other['id'] == event['id'] or other['fim'] is None:
            continue
        a, b = datetime.fromisoformat(other['inicio']), datetime.fromisoformat(other['fim'])
        if b <= start:
            before = max(before, b+guard)
        if a >= end:
            after = min(after, a-guard)
    if before <= t < start-guard:
        return 'antes'
    if start+guard < t < end-guard:
        return 'durante'
    if end+guard < t <= after:
        return 'depois'
    return 'fora_da_janela'


def fraction(points, minimum, ready=True):
    n, alerts = len(points), sum(p['alerta'] for p in points)
    enough = ready and n >= minimum
    return {'n': n, 'alertas': alerts, 'taxa_alertas': alerts/n if enough and n else None,
            'dados_suficientes': enough, 'minimo_registros': minimum}


def event_metrics(points, events):
    output = []
    for event in events:
        metrics = {'evento_id': event['id'], 'descricao': event['descricao'],
                   'inicio': event['inicio'], 'fim': event['fim'], 'periodos': {}}
        if event['fim'] is None:
            metrics['status'] = 'evento_aberto'
        else:
            groups = {phase: [] for phase in ('antes','durante','depois','fronteira_incerta','fora_da_janela')}
            for point in points:
                groups[event_phase(point['instante'], event, events)].append(point)
            for phase in ('antes', 'durante', 'depois'):
                metrics['periodos'][phase] = fraction(groups[phase], MIN_PERIOD_SAMPLES)
            metrics['fronteiras_incertas'] = len(groups['fronteira_incerta'])
            metrics['fora_da_janela'] = len(groups['fora_da_janela'])
            metrics['status'] = ('disponivel' if all(x['dados_suficientes'] for x in metrics['periodos'].values())
                                 else 'dados_insuficientes')
        output.append(metrics)
    return output


def evaluate(conn, eid, comparison_id=None):
    exp = protocol.experiment_summary(conn, eid)
    if comparison_id is None:
        last = conn.execute('SELECT comparacao_id FROM modelos_ml WHERE experimento_id=? '
                            'ORDER BY criado_em DESC,id DESC LIMIT 1', (eid,)).fetchone()
        comparison_id = last[0] if last else None
    models = conn.execute('SELECT * FROM modelos_ml WHERE experimento_id=? AND comparacao_id=? '
                          'ORDER BY variante', (eid, comparison_id)).fetchall()
    if comparison_id is not None and {r['variante'] for r in models} != set(FEATURE_SETS):
        raise protocol.ProtocolError('Comparacao nao encontrada ou par de modelos incompleto', 404)
    if models:
        score_closed_sessions(conn, models, exp['sessoes'])
    report = {'schema_version': 1, 'gerado_em': protocol.iso(protocol.utc_now()),
        'experimento': exp, 'comparacao_id': comparison_id, 'modelos': [], 'pontos': [],
        'dados_suficientes': False, 'status': 'dados_insuficientes',
        'metodologia': {'treino': 'exclusivamente NORMAL_01', 'score': 'menor = mais incomum',
            'limiar_decisao': 0, 'alerta': 'score_decisao < 0', 'minimo_por_periodo': MIN_PERIOD_SAMPLES,
            'janela_evento_s': EVENT_WINDOW_S, 'guarda_evento_s': EVENT_GUARD_S,
            'tempo': 'recepcao UTC; sem timestamp de aquisicao no firmware',
            'limite': 'Taxas descritivas de alerta; nao representam diagnostico ou sensibilidade a falhas'}}
    for model in models:
        metadata = model_metadata(conn, model)
        metadata['sessoes'] = []
        for session in exp['sessoes']:
            points = [dict(r) for r in conn.execute(
                'SELECT s.*,m.instante,m.rms,m.amplitude,m.pico_fft FROM ml_scores s '
                'JOIN medicoes m ON m.id=s.medicao_id WHERE s.modelo_id=? AND s.sessao_id=? '
                'ORDER BY m.instante,m.id', (model['id'], session['id']))]
            for point in points:
                point.update(codigo_sessao=session['codigo'], variante=model['variante'])
                point['periodos_eventos'] = [{'evento_id': event['id'],
                    'periodo': event_phase(point['instante'], event, session['eventos'])}
                    for event in session['eventos'] if event['fim'] is not None]
            report['pontos'].extend(points)
            has_events = session['codigo'] != 'TOQUE_01' or bool(session['eventos'])
            summary = {**fraction(points, session['minimo_avaliacao'], session['dados_suficientes'] and has_events),
                'sessao_id': session['id'], 'codigo': session['codigo'],
                'papel': 'ajuste_treinamento' if session['codigo']=='NORMAL_01' else 'avaliacao_separada',
                'tipo': ('normal' if session['codigo'] in ('NORMAL_01','NORMAL_02','RETORNO_01')
                         else 'mista_com_eventos' if session['codigo']=='TOQUE_01' else 'mudanca_experimental'),
                'estado_coleta': session['estado'], 'registros_excluidos': session['registros_excluidos'],
                'eventos': event_metrics(points, session['eventos'])}
            summary['status'] = 'disponivel' if summary['dados_suficientes'] else 'dados_insuficientes'
            metadata['sessoes'].append(summary)
        report['modelos'].append(metadata)
    report['avaliacao_sessoes_suficiente'] = bool(models) and all(
        s['dados_suficientes'] for m in report['modelos'] for s in m['sessoes'])
    report['analise_eventos_suficiente'] = bool(models) and all(
        bool(s['eventos']) and all(e['status']=='disponivel' for e in s['eventos'])
        for m in report['modelos'] for s in m['sessoes'] if s['codigo']=='TOQUE_01')
    if report['avaliacao_sessoes_suficiente'] and report['analise_eventos_suficiente']:
        report['dados_suficientes'] = True
        report['status'] = 'avaliacao_descritiva_disponivel'
    if not models:
        report['mensagem'] = 'Dados insuficientes: conclua NORMAL_01 e treine o par de modelos.'
    elif not report['dados_suficientes']:
        report['mensagem'] = 'Protocolo incompleto: taxas ausentes nao significam zero alertas.'
    else:
        report['mensagem'] = 'Comparacao descritiva disponivel; nao diagnostica falhas mecanicas.'
    return report
