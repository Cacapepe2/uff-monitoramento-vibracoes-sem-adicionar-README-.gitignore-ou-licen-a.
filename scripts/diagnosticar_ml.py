"""Auditoria offline de snapshot local confiavel. Nao escreve no SQLite nem faz fit de IF.

Uso: python scripts/diagnosticar_ml.py --snapshot <backup-local> --saida <pasta-nova>
Dependencias: requirements-diagnostico.txt. Pickle somente do banco local confiavel.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import sklearn
from scipy.stats import spearmanr

from analytics.diagnostics import (FEATURES, audit_model, describe, distribution_shift,
                                   fit_statistical_baseline, matrix, statistical_scores)
from backend import experiments

NORMALS = ('NORMAL_01', 'NORMAL_02', 'RETORNO_01')
LABELS = ('RMS (m/s²)', 'Amplitude (m/s²)', 'Pico dominante (Hz)')
COLORS = ('#176B9A', '#D97415', '#16856B')


def fingerprint(conn, eid):
    models = [list(r) for r in conn.execute('SELECT * FROM modelos_ml WHERE experimento_id=? ORDER BY id', (eid,))]
    for row in models:
        row[-2] = hashlib.sha256(row[-2]).hexdigest()  # BLOB artefato, nao exportar pickle
    scores = [list(r) for r in conn.execute('SELECT s.* FROM ml_scores s JOIN modelos_ml m '
        'ON m.id=s.modelo_id WHERE m.experimento_id=? ORDER BY s.modelo_id,s.medicao_id', (eid,))]
    memberships = [list(r) for r in conn.execute('SELECT t.* FROM ml_treino t JOIN modelos_ml m '
        'ON m.id=t.modelo_id WHERE m.experimento_id=? ORDER BY t.modelo_id,t.medicao_id', (eid,))]
    payload = json.dumps([models, scores, memberships], separators=(',', ':'), ensure_ascii=False)
    return {'sha256': hashlib.sha256(payload.encode()).hexdigest(),
            'modelos': len(models), 'scores': len(scores), 'vinculos_treino': len(memberships)}


def plot_figures(output, sessions, audits, baseline):
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})

    def save(fig, name):
        fig.savefig(output/(name+'.png'), dpi=160, bbox_inches='tight')
        fig.savefig(output/(name+'.svg'), bbox_inches='tight')
        plt.close(fig)

    fig, axes = plt.subplots(3, 2, figsize=(12, 11), layout='constrained')
    for j, f in enumerate(FEATURES):
        values = [[r[f] for r in sessions[code]] for code in NORMALS]
        axes[j, 0].boxplot(values, tick_labels=NORMALS, showmeans=True)
        axes[j, 0].set_ylabel(LABELS[j])
        for color, code, x in zip(COLORS, NORMALS, values):
            ordered = np.sort(x)
            axes[j, 1].step(ordered, np.arange(1, len(x)+1)/len(x), where='post', color=color, label=code)
        axes[j, 1].set(xlabel=LABELS[j], ylabel='Fração acumulada', ylim=(0, 1.03))
        axes[j, 1].legend(fontsize=9)
    fig.suptitle('Distribuições nas sessões declaradas normais — dados físicos', fontsize=15)
    save(fig, '01_distribuicoes')

    fig, axes = plt.subplots(3, 3, figsize=(14, 10), layout='constrained')
    for i, code in enumerate(NORMALS):
        rows = sessions[code]
        start = datetime.fromisoformat(rows[0]['instante'])
        minutes = [(datetime.fromisoformat(r['instante'])-start).total_seconds()/60 for r in rows]
        for j, f in enumerate(FEATURES):
            axes[i, j].plot(minutes, [r[f] for r in rows], '.-', color=COLORS[i], ms=3, lw=1)
            axes[i, j].set(xlabel='Minutos desde 1ª recepção', ylabel=LABELS[j], title=code)
    fig.suptitle('Evolução temporal dentro de cada sessão — escalas próprias por painel', fontsize=14)
    save(fig, '02_tempo_features')

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout='constrained')
    for i, code in enumerate(NORMALS):
        x = matrix(sessions[code], ('rms', 'amplitude'))
        axes[0].scatter(x[:, 0], x[:, 1], s=22, alpha=.65, color=COLORS[i], label=code)
    lo, hi = baseline['inferior'], baseline['superior']
    axes[0].plot([lo[0], hi[0], hi[0], lo[0], lo[0]], [lo[1], lo[1], hi[1], hi[1], lo[1]],
                 '--', color='black', label='Limites treino: média ± 3s')
    axes[0].set(xlabel=LABELS[0], ylabel=LABELS[1], title='Espaço conjunto, sem reescala')
    axes[0].legend(fontsize=8)
    x = matrix(sessions['NORMAL_01'], ('rms', 'amplitude'))
    points = axes[1].scatter(x[:, 0], x[:, 1], c=np.arange(len(x)), cmap='viridis', s=28)
    axes[1].set(xlabel=LABELS[0], ylabel=LABELS[1], title='NORMAL_01: ordem de recepção')
    fig.colorbar(points, ax=axes[1], label='Índice no treino (0–99)')
    save(fig, '03_espaco_conjunto')

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), layout='constrained')
    palette = plt.get_cmap('tab10')
    for i, audit in enumerate(audits):
        for j, (code, scores) in enumerate(audit['sessoes'].items()):
            rows = sessions[code]
            t0 = datetime.fromisoformat(rows[0]['instante'])
            t = [(datetime.fromisoformat(r['instante'])-t0).total_seconds()/60 for r in rows]
            axes[i, 0].plot(t, scores['decision'], '.-', color=palette(j), label=code, ms=3, lw=.8)
        axes[i, 0].axhline(0, color='black', ls='--', label='Limiar preservado')
        axes[i, 0].set(xlabel='Minutos desde 1ª recepção de cada sessão', ylabel='decision_function',
                       title=audit['variante'])
        axes[i, 0].legend(fontsize=8, ncol=2)
        axes[i, 1].boxplot([audit['sessoes'][code]['decision'] for code in sessions],
                          tick_labels=list(sessions), showmeans=True)
        axes[i, 1].tick_params(axis='x', rotation=35)
        axes[i, 1].axhline(0, color='black', ls='--')
        axes[i, 1].set(ylabel='decision_function', title='Menor = mais incomum; não é probabilidade')
    fig.suptitle('Scores contínuos dos modelos existentes — sem novo ajuste', fontsize=15)
    save(fig, '04_scores_continuos')


def run(snapshot, output):
    source = ROOT/'docs/evidencias_ml/avaliacao_fisica.json'
    original = json.loads(source.read_text(encoding='utf-8'))
    eid, comparison = original['experimento']['id'], original['comparacao_id']
    conn = sqlite3.connect(snapshot.resolve().as_uri()+'?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    before = fingerprint(conn, eid)
    exp = experiments.experiment_summary(conn, eid)
    sessions = {s['codigo']: experiments.session_measurements(conn, s['id'], True) for s in exp['sessoes']}
    if any(s['estado'] != 'encerrada' for s in exp['sessoes']):
        raise ValueError('Sessao ainda aberta: auditar somente campanha encerrada')
    output.mkdir(parents=True, exist_ok=False)
    stats, shifts, temporal, baseline_scores = {}, {}, {}, {}
    baseline = fit_statistical_baseline(sessions['NORMAL_01'])
    for code, rows in sessions.items():
        x = matrix(rows, FEATURES)
        stats[code] = {f: describe(x[:, j]) for j, f in enumerate(FEATURES)}
        shifts[code] = {f: distribution_shift([r[f] for r in sessions['NORMAL_01']], x[:, j])
                        for j, f in enumerate(FEATURES)}
        temporal[code] = {}
        start = datetime.fromisoformat(rows[0]['instante'])
        minutes = np.array([(datetime.fromisoformat(r['instante'])-start).total_seconds()/60 for r in rows])
        for j, f in enumerate(FEATURES):
            v = x[:, j]
            variable = np.ptp(v) > 0
            temporal[code][f] = {'media_primeiros20': float(v[:20].mean()),
                'media_ultimos20': float(v[-20:].mean()),
                'rho_spearman_tempo': float(spearmanr(minutes, v).statistic) if variable else None,
                'correlacao_lag1': float(np.corrcoef(v[:-1], v[1:])[0, 1]) if variable else None,
                'inclinacao_por_minuto': float(np.polyfit(minutes, v, 1)[0]) if variable else 0.0,
                'contagem_valores': dict(Counter(str(value) for value in v)) if f == 'pico_fft' else None}
        margin, alerts = statistical_scores(baseline, rows)
        baseline_scores[code] = {'ids': [r['id'] for r in rows], 'margem': margin.tolist(),
            'alertas': int(alerts.sum()), 'n': len(rows), 'taxa_alertas': float(alerts.mean()),
            'margem_resumo': describe(margin)}
    models = conn.execute('SELECT * FROM modelos_ml WHERE comparacao_id=? ORDER BY variante', (comparison,)).fetchall()
    audits = [audit_model(conn, row, sessions) for row in models]
    assert len(audits) == 2
    for audit in audits:
        points = [p for p in original['pontos'] if p['modelo_id'] == audit['modelo_id']]
        expected = {mid: value for session in audit['sessoes'].values()
                    for mid, value in zip(session['ids'], session['decision'])}
        audit['checks']['relatorio_original_reproduzido'] = (len(points) == len(expected) and
            all(abs(p['score_decisao']-expected[p['medicao_id']]) < 1e-12 for p in points))
        audit['todos_checks_ok'] = all(audit['checks'].values())
    assert all(a['todos_checks_ok'] for a in audits), 'Auditoria reprovada; investigar antes de interpretar'
    model_similarity = {code: {'correlacao_pearson_scores': (float(np.corrcoef(
        audits[0]['sessoes'][code]['decision'], audits[1]['sessoes'][code]['decision'])[0, 1])
        if all(np.ptp(a['sessoes'][code]['decision']) > 0 for a in audits) else None),
        'mediana_delta_3features_menos_2features': float(np.median(np.array(
            audits[1]['sessoes'][code]['decision'])-audits[0]['sessoes'][code]['decision']))}
        for code in sessions}
    artifact_sources = json.loads(models[0]['ambiente_json'])['source_sha256']
    preservation = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest
                    for name, digest in artifact_sources.items()}
    assert fingerprint(conn, eid) == before
    assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    report = {'gerado_em': datetime.now(timezone.utc).isoformat(), 'experimento_id': eid,
        'comparacao_id': comparison, 'metodo': 'Auditoria somente leitura; IF sem fit e sem alterar limiar',
        'ambiente': {'numpy': np.__version__, 'sklearn': sklearn.__version__, 'matplotlib': matplotlib.__version__},
        'estatisticas': stats, 'deslocamentos': shifts, 'tempo': temporal, 'modelos': audits,
        'comparacao_scores': model_similarity, 'baseline_estatistico': baseline,
        'baseline_sessoes': baseline_scores, 'preservacao': {'banco_snapshot': before,
        'fontes_iguais_ao_treino': preservation,
        'avaliacao_original_sha256': hashlib.sha256(source.read_bytes()).hexdigest()},
        'limitacoes': ['KS e Wasserstein sao distancias descritivas; sem teste de significancia IID.',
            '3 desvios e uma regra declarada, sem garantia nominal de falso alarme.',
            'Causa fisica e tamanho de treino suficiente nao sao identificaveis com esta unica campanha.',
            'Nenhum parametro ajustado com NORMAL_02/RETORNO_01. Baseline nao substitui os modelos.']}
    (output/'auditoria.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    plot_figures(output, sessions, audits, baseline)
    print('Auditoria concluida: artefatos originais, scores e pre-processamento conferidos.')
    for code, values in baseline_scores.items():
        print(code, '| baseline 3s:', f"{values['alertas']}/{values['n']}")
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--saida', type=Path, default=ROOT/'docs/evidencias_ml/diagnostico')
    args = parser.parse_args()
    run(args.snapshot, args.saida)
