"""Fixtures temporarias; nao representam desempenho do hardware."""
import json
from contextlib import closing

import numpy as np
import pytest

from analytics.diagnostics import (audit_model, describe, distribution_shift,
                                   fit_statistical_baseline, matrix, statistical_scores)
from backend import experiments
from backend.database import connect
from test_experimentos import collect, rig
from test_ml_experimental import evaluate, train


def test_baseline_fit_somente_treino_e_limites_bilaterais():
    rows = [{'id': i, 'rms': float(i), 'amplitude': float(2*i)} for i in range(1, 6)]
    baseline = fit_statistical_baseline(rows)
    assert baseline['ids_treino'] == [1, 2, 3, 4, 5]
    assert np.allclose(baseline['desvio_padrao'], [np.std(range(1, 6), ddof=1), 2*np.std(range(1, 6), ddof=1)])
    before = json.dumps(baseline, sort_keys=True)
    margin, flags = statistical_scores(baseline, [{'rms': 3, 'amplitude': 6}, {'rms': 100, 'amplitude': 6},
                                                {'rms': 3, 'amplitude': 100}])
    assert flags.tolist() == [False, True, True]
    assert np.array_equal(margin < 0, flags)
    assert json.dumps(baseline, sort_keys=True) == before


@pytest.mark.parametrize('value', [None, float('nan'), float('inf'), -1])
def test_sem_imputacao_silenciosa(value):
    with pytest.raises(ValueError):
        matrix([{'rms': value, 'amplitude': 1}], ['rms', 'amplitude'])


def test_variancia_zero_nao_vira_limite_arbitrario():
    with pytest.raises(ValueError, match='Variancia zero'):
        fit_statistical_baseline([{'id': 1, 'rms': 1, 'amplitude': 1},
                                  {'id': 2, 'rms': 1, 'amplitude': 2}])


def test_estatisticas_e_deslocamento_nao_confundem_escala_com_causa():
    summary = describe([1, 2, 3, 4, 5])
    assert summary['mediana'] == 3
    assert summary['desvio_padrao'] == pytest.approx(np.std([1, 2, 3, 4, 5], ddof=1))
    shift = distribution_shift(np.array([1, 2, 3]), np.array([11, 12, 13]))
    assert shift['wasserstein'] == pytest.approx(10)
    assert shift['ks_distancia'] == 1
    assert shift['fora_min_max_treino'] == 3
    assert not any('pvalor' in k for k in shift)


def test_auditoria_reproduz_scores_e_detecta_troca_de_features(rig):
    client, db, clock, exp = rig
    collect(client, clock, exp, 'NORMAL_01', 100)
    train(client, exp)
    collect(client, clock, exp, 'NORMAL_02', 50, shift=10)
    evaluate(client, exp)
    with closing(connect(db)) as conn:
        sessions = {code: experiments.session_measurements(conn, next(
            s['id'] for s in exp['sessoes'] if s['codigo'] == code), True)
            for code in ('NORMAL_01', 'NORMAL_02')}
        row = conn.execute("SELECT * FROM modelos_ml WHERE variante='rms_amplitude'").fetchone()
        audit = audit_model(conn, row, sessions)
        assert audit['todos_checks_ok']
        assert audit['erro_maximo_scores'] == 0
        changed = dict(row)
        changed['features_json'] = json.dumps(['amplitude', 'rms'])
        bad = audit_model(conn, changed, sessions)
        assert not bad['todos_checks_ok']
        assert not bad['checks']['features_ordem_contrato']
        assert not bad['checks']['scaler_media_somente_treino']
