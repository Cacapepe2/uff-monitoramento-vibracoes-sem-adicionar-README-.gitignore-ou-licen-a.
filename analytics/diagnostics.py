"""Diagnosticos descritivos; nao altera nem recalibra modelos de producao."""
import hashlib
import json

import numpy as np
from scipy.stats import ks_2samp, wasserstein_distance

from .isolation import FEATURE_SETS, canonical, load_model
from backend import experiments

FEATURES = ('rms', 'amplitude', 'pico_fft')


def matrix(rows, features):
    """Mesma ordem explicita do contrato, sem imputacao ou descarte silencioso."""
    if not rows:
        raise ValueError('Conjunto vazio')
    x = np.asarray([[r[f] for f in features] for r in rows], dtype=float)
    if not np.isfinite(x).all() or (x < 0).any():
        raise ValueError('Features ausentes, nao finitas ou negativas')
    return x


def describe(values):
    x = np.asarray(values, dtype=float)
    if x.size < 2 or not np.isfinite(x).all():
        raise ValueError('Estatistica exige pelo menos dois valores finitos')
    return dict(n=int(x.size), media=float(x.mean()), desvio_padrao=float(x.std(ddof=1)),
                minimo=float(x.min()), q05=float(np.quantile(x, .05)),
                q25=float(np.quantile(x, .25)), mediana=float(np.median(x)),
                q75=float(np.quantile(x, .75)), q95=float(np.quantile(x, .95)),
                maximo=float(x.max()))


def distribution_shift(training, evaluation):
    """KS apenas como distancia empirica: sem p-valor que suponha IID."""
    a, b = np.asarray(training), np.asarray(evaluation)
    sd = float(a.std(ddof=1))
    return {'delta_media': float(b.mean()-a.mean()),
            'delta_mediana_pct': float(100*(np.median(b)/np.median(a)-1)) if np.median(a) else None,
            'delta_media_em_sd_treino': float((b.mean()-a.mean())/sd) if sd else None,
            'wasserstein': float(wasserstein_distance(a, b)),
            'ks_distancia': float(ks_2samp(a, b).statistic),
            'fora_min_max_treino': int(((b < a.min()) | (b > a.max())).sum())}


def fit_statistical_baseline(training, k=3.0):
    """Regra fixa bilateral media +/- 3 desvios amostrais; fit somente treino.

    Nao assume taxa nominal de falso alarme: dados nao sao IID/gaussianos.
    Variancia zero exige outro protocolo explicito, nao um epsilon arbitrario.
    """
    x = matrix(training, ('rms', 'amplitude'))
    if len(x) < 2 or k <= 0:
        raise ValueError('Treino ou multiplicador invalido')
    mean, sd = x.mean(axis=0), x.std(axis=0, ddof=1)
    if (sd == 0).any():
        raise ValueError('Variancia zero: nao definir limite artificial')
    return {'features': ['rms', 'amplitude'], 'k': float(k), 'ddof': 1,
            'media': mean.tolist(), 'desvio_padrao': sd.tolist(),
            'inferior': np.maximum(0, mean-k*sd).tolist(), 'superior': (mean+k*sd).tolist(),
            'ids_treino': [r['id'] for r in training]}


def statistical_scores(model, rows):
    x = matrix(rows, model['features'])
    z = np.abs((x-np.array(model['media']))/np.array(model['desvio_padrao']))
    # Margem negativa = alerta, como decision_function; nao e probabilidade.
    margin = model['k']-z.max(axis=1)
    return margin, margin < 0


def audit_model(conn, row, sessions):
    """Carrega artefato local com hash verificado e recalcula sem fit nem escrita."""
    model = load_model(row)
    features = json.loads(row['features_json'])
    training = sessions['NORMAL_01']
    x = matrix(training, features)
    scaler, forest = model[0], model[-1]
    ids = sorted(r[0] for r in conn.execute(
        'SELECT medicao_id FROM ml_treino WHERE modelo_id=?', (row['id'],)))
    snapshot = {'sessao': experiments.session_summary(conn, row['sessao_treino_id']),
                'medicoes': training}
    expected_scale = np.sqrt(x.var(axis=0))
    expected_scale[expected_scale == 0] = 1
    parameters = json.loads(row['parametros_json'])
    checks = {
        'features_ordem_contrato': features == FEATURE_SETS[row['variante']],
        'somente_100_ids_NORMAL_01': ids == sorted(r['id'] for r in training) and len(ids) == 100,
        'snapshot_treino_sha256': hashlib.sha256(canonical(snapshot).encode()).hexdigest() == row['dados_sha256'],
        'pipeline_duas_etapas': len(model.steps) == 2,
        'scaler_media_somente_treino': bool(np.allclose(scaler.mean_, x.mean(axis=0), rtol=1e-12)),
        'scaler_variancia_ddof0': bool(np.allclose(scaler.var_, x.var(axis=0), rtol=1e-12)),
        'scaler_escala': bool(np.allclose(scaler.scale_, expected_scale, rtol=1e-12)),
        'scaler_100_observacoes': bool(np.all(np.asarray(scaler.n_samples_seen_) == 100)),
        'numero_features': scaler.n_features_in_ == forest.n_features_in_ == len(features),
        'offset_auto_menos_05': forest.contamination == 'auto' and forest.offset_ == -.5,
        'parametros_persistidos': all(forest.get_params()[k] == parameters[k]
                                    for k in ('contamination', 'n_estimators', 'max_samples', 'random_state', 'n_jobs')),
        'offset_metadados': forest.offset_ == parameters['offset'],
    }
    scores, max_error = {}, 0.0
    for code, rows in sessions.items():
        data = matrix(rows, features)
        raw, decision, predicted = model.score_samples(data), model.decision_function(data), model.predict(data)
        z = scaler.transform(data)
        saved = {r['medicao_id']: r for r in conn.execute(
            'SELECT * FROM ml_scores WHERE modelo_id=?', (row['id'],))}
        stored_raw = np.array([saved[r['id']]['score_bruto'] for r in rows])
        stored_decision = np.array([saved[r['id']]['score_decisao'] for r in rows])
        max_error = max(max_error, float(np.max(np.abs(raw-stored_raw))),
                        float(np.max(np.abs(decision-stored_decision))))
        checks[code+'_score_samples_reproduzido'] = bool(np.allclose(raw, stored_raw, rtol=0, atol=1e-12))
        checks[code+'_decision_reproduzido'] = bool(np.allclose(decision, stored_decision, rtol=0, atol=1e-12))
        checks[code+'_algebra_offset'] = bool(np.allclose(decision, raw-forest.offset_, rtol=0, atol=1e-12))
        checks[code+'_predict_equivalente'] = bool(np.array_equal(predicted == -1, decision < 0))
        checks[code+'_alertas_persistidos'] = all(int(v < 0) == saved[r['id']]['alerta'] for r, v in zip(rows, decision))
        checks[code+'_pipeline_sem_dupla_escala'] = bool(np.allclose(raw, forest.score_samples(z), rtol=0, atol=1e-12))
        scores[code] = {'raw': raw.tolist(), 'decision': decision.tolist(), 'predict': predicted.tolist(),
                        'ids': [r['id'] for r in rows], 'score_resumo': describe(decision),
                        'z_media': z.mean(axis=0).tolist(), 'alertas': int((predicted == -1).sum()),
                        'taxa_alertas': float((predicted == -1).mean())}
    return {'modelo_id': row['id'], 'variante': row['variante'], 'features': features,
            'artefato_sha256': row['artefato_sha256'], 'checks': checks,
            'todos_checks_ok': all(checks.values()), 'erro_maximo_scores': max_error,
            'scaler_media': scaler.mean_.tolist(), 'scaler_escala': scaler.scale_.tolist(),
            'offset': float(forest.offset_), 'max_samples_efetivo': int(forest.max_samples_),
            'sessoes': scores}
