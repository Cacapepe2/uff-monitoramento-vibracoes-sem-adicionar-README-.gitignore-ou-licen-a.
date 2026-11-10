"""Graficos a partir de JSON de resultados; nao carrega banco nem modelos pickle."""
import html
import json
import math
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots


def validate_report(report):
    if not isinstance(report, dict) or report.get('schema_version') != 1:
        raise ValueError('Formato de relatorio experimental nao reconhecido')
    for key in ('experimento', 'modelos', 'pontos', 'metodologia', 'status', 'mensagem', 'dados_suficientes'):
        if key not in report:
            raise ValueError(f'Relatorio incompleto: {key}')
    if not isinstance(report['pontos'], list) or len(report['pontos']) > 200000:
        raise ValueError('Quantidade de pontos invalida')
    if not isinstance(report['modelos'], list) or not isinstance(report['experimento'], dict):
        raise ValueError('Estrutura de modelos/experimento invalida')
    for point in report['pontos']:
        for field in ('score_decisao', 'score_bruto'):
            value = point.get(field)
            if not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError('Score nao finito no relatorio')
    return report


def charts(report, session_code=None, period=None):
    validate_report(report)
    models = report['modelos']
    points = [p for p in report['pontos'] if not session_code or p['codigo_sessao'] == session_code]
    if period:
        points = [p for p in points if any(x['periodo'] == period for x in p['periodos_eventos'])]
    if not models or not points:
        return {}
    codes = [s['codigo'] for s in report['experimento']['sessoes']]
    colors = dict(zip(codes, ['#167d8d', '#4263eb', '#d97706', '#9c5c31', '#a21caf', '#15803d']))
    timeline = make_subplots(rows=len(models), cols=1, shared_xaxes=True,
                             subplot_titles=[m['variante'] for m in models])
    distribution, rates = go.Figure(), go.Figure()
    for row, model in enumerate(models, 1):
        for code in codes:
            selected = [p for p in points if p['modelo_id'] == model['id'] and p['codigo_sessao'] == code]
            if not selected:
                continue
            selected.sort(key=lambda p: (p['instante'], p['medicao_id']))
            label = code+' (treino)' if code=='NORMAL_01' else code
            timeline.add_trace(go.Scatter(
                x=[p['instante'] for p in selected], y=[p['score_decisao'] for p in selected],
                mode='lines+markers', name=label, legendgroup=code, showlegend=row==1,
                line={'color': colors[code]},
                customdata=[[p['medicao_id'], p['sessao_id'], p['modelo_id'], p['alerta'],
                             p['rms'], p['amplitude'], p['pico_fft']] for p in selected],
                hovertemplate=('ID=%{customdata[0]} | sessao=%{customdata[1]}<br>modelo=%{customdata[2]}'
                    '<br>%{x}<br>score=%{y:.4f}, alerta=%{customdata[3]}'
                    '<br>RMS=%{customdata[4]:.6f}, amp=%{customdata[5]:.6f}'
                    '<br>pico=%{customdata[6]:.6f} Hz<extra></extra>')), row=row, col=1)
            distribution.add_trace(go.Box(y=[p['score_decisao'] for p in selected],
                name=label+' / '+model['variante'], boxpoints='all', jitter=.25,
                marker={'color': colors[code]}, legendgroup=model['id']))
        timeline.add_hline(y=0, line_dash='dash', line_color='#b91c1c', row=row, col=1)
        summaries = [s for s in model['sessoes'] if not session_code or s['codigo'] == session_code]
        rates.add_trace(go.Bar(name=model['variante'],
            x=[s['codigo']+' (treino)' if s['codigo']=='NORMAL_01' else s['codigo'] for s in summaries],
            y=[s['taxa_alertas'] for s in summaries],
            text=[f"{s['alertas']}/{s['n']}" if s['dados_suficientes'] else 'Dados insuficientes'
                  for s in summaries], textposition='auto'))
    for session in report['experimento']['sessoes']:
        if session_code and session['codigo'] != session_code:
            continue
        for event in session['eventos']:
            if event['fim']:
                timeline.add_vrect(x0=event['inicio'], x1=event['fim'], fillcolor='#f59e0b',
                                  opacity=.15, line_width=0)
    timeline.update_layout(height=320*len(models), title='Scores por recepcao UTC; menor = mais incomum')
    timeline.update_yaxes(title_text='decision_function')
    distribution.add_hline(y=0, line_dash='dash', line_color='#b91c1c')
    distribution.update_layout(title='Distribuicao dos scores por sessao/condicao', height=550)
    rates.update_layout(title='Taxas descritivas por sessao (ausente = dados insuficientes)',
                        barmode='group', yaxis={'tickformat': '.0%', 'range': [0, 1]}, height=450)
    result = {'tempo': timeline, 'condicoes': distribution}
    # Um filtro por periodo nao deve exibir taxa global como se fosse daquela fase.
    if not period:
        result['taxas'] = rates
    return result


def write_html(report, path):
    validate_report(report)
    graphs = charts(report)
    title = html.escape(report['experimento']['nome'])
    parts = [f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>{title}</title>',
        '<style>body{font:16px system-ui;max-width:1250px;margin:2rem auto;padding:0 1rem}'
        'pre{white-space:pre-wrap}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:.5rem}</style>',
        f'<h1>{title}</h1><p>{html.escape(report["mensagem"])}</p>',
        '<p>Desvios de padrao; nenhuma classificacao de falha mecanica. '
        'Treino exclusivamente NORMAL_01. Horarios de recepcao em UTC.</p>']
    if not graphs:
        parts.append('<p><strong>Dados insuficientes para visualizar scores.</strong></p>')
    for index, figure in enumerate(graphs.values()):
        parts.append(figure.to_html(full_html=False, include_plotlyjs=True if index==0 else False))
    parts.append('<h2>Periodos dos eventos (tempos aproximados por recepcao)</h2>')
    for model in report['modelos']:
        for session in model['sessoes']:
            for event in session['eventos']:
                data = {'variante': model['variante'], 'sessao': session['codigo'], **event}
                parts.append('<pre>'+html.escape(json.dumps(data, ensure_ascii=False, indent=2))+'</pre>')
    parts.append('<p>Linhas sombreadas/intervalos indicam eventos declarados; '
                 'uma amostra enviada a cada ~5 s nao garante capturar transitorios.</p></html>')
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('\n'.join(parts), encoding='utf-8')
