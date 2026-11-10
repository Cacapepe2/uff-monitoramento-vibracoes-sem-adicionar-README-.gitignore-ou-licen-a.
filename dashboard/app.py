"""Dashboard somente leitura de relatorio JSON; pronto para evolucao, sem deploy."""
import json
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analytics.visualization import charts, validate_report

st.set_page_config(page_title='Experimentos de vibracao', layout='wide')
st.title('Desvios de vibracao por sessao experimental')
st.caption('Isolation Forest: comparacao experimental. Nenhum diagnostico de falha mecanica.')
uploaded = st.file_uploader('Relatorio JSON gerado pelo cliente experimental', type=['json'])
local = Path(os.environ.get('EXPERIMENT_REPORT_PATH',
    str(Path(__file__).resolve().parent.parent/'.marco3_local/relatorio_experimental.json')))
if uploaded is None and not local.exists():
    st.info('Dados insuficientes: carregue um relatorio. Nenhuma sessao ou medicao e criada pelo dashboard.')
    st.stop()
try:
    raw = uploaded.getvalue() if uploaded is not None else local.read_bytes()
    if len(raw) > 25_000_000:
        raise ValueError('Relatorio maior que 25 MB')
    report = validate_report(json.loads(raw))
except (ValueError, TypeError, KeyError) as exc:
    st.error('Relatorio invalido: '+str(exc))
    st.stop()
st.subheader(report['experimento']['nome'])
if report['dados_suficientes']:
    st.success(report['mensagem'])
else:
    st.warning(report['mensagem'])
st.caption('Tempo no eixo = recepcao UTC. Treino somente NORMAL_01; NORMAL_02 e RETORNO_01 separados.')
rows = []
for model in report['modelos']:
    for summary in model['sessoes']:
        rows.append({'variante': model['variante'], 'sessao': summary['codigo'],
            'papel': summary['papel'], 'n': summary['n'], 'alertas': summary['alertas'],
            'taxa_alertas': summary['taxa_alertas'], 'status': summary['status']})
if rows:
    st.dataframe(rows, hide_index=True)
else:
    st.info('Sem modelos treinados: NORMAL_01 precisa ter 100 registros elegiveis e estar encerrada.')
codes = ['Todas']+[s['codigo'] for s in report['experimento']['sessoes']]
selected = st.selectbox('Sessao', codes)
phase = st.selectbox('Periodo relativo aos eventos', ['Todos','antes','durante','depois','fronteira_incerta'])
figures = charts(report, None if selected=='Todas' else selected, None if phase=='Todos' else phase)
for figure in figures.values():
    st.plotly_chart(figure, use_container_width=True)
if not figures:
    st.info('Sem scores neste filtro. Ausencia de pontos ou de taxas nao significa ausencia de desvios.')
with st.expander('Eventos, periodos e rastreabilidade'):
    for model in report['modelos']:
        for summary in model['sessoes']:
            if summary['eventos']:
                st.write(model['variante'], summary['codigo'])
                st.json(summary['eventos'])
    st.dataframe(report['pontos'], hide_index=True)
    st.caption('Cada ponto conserva modelo_id, sessao_id e medicao_id. '
               'Fronteiras de eventos usam guarda de 5 s; nao ha timestamp da aquisicao.')
st.warning('Janelas de 0,512 s enviadas a cada ~5 s podem perder eventos transitorios. '
           'As taxas sao descritivas; amostras de uma mesma sessao nao sao repeticoes independentes.')
