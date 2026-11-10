"""Entrypoint Community Cloud. Leitura anonima Supabase ou replay real identificado."""
import os
import sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import plotly.graph_objects as go
import streamlit as st
from cloud_sync.public_data import ML_WARNING,validate_document
from cloud_sync.transport import Supabase
from dashboard.public_view import bundled,measurement_state,replay_window,unpack,brazil_time,brazil_rows

st.set_page_config(page_title='Atividade de Extensão de Sistema de Computação',page_icon='📈',layout='wide')
st.markdown('''<style>
.stApp {background:#F8FAFC;color:#183153}
.block-container {max-width:1250px;padding-top:2rem;padding-bottom:3rem}
h1,h2,h3 {color:#183153!important}
div[data-testid="stMetric"] {background:white;border:1px solid #EAF1F7;border-top:3px solid #2463A6;
border-radius:12px;padding:1rem}
div[data-testid="stSidebar"] {background:#EAF1F7}
.intro {color:#188778;font-weight:600;font-size:1.15rem;margin-bottom:1.5rem}
@media(max-width:640px){.block-container{padding:1rem}h1{font-size:1.7rem!important}
div[data-testid="stHorizontalBlock"]{flex-wrap:wrap}
div[data-testid="stColumn"]{min-width:100%!important;flex:100%!important}}
</style>''',unsafe_allow_html=True)
st.title('Atividade de Extensão de Sistema de Computação')
st.markdown('<div class="intro">Monitoramento Inteligente de Vibrações com ESP32 e Machine Learning</div>',unsafe_allow_html=True)
st.warning(ML_WARNING)


def config(name):
    try:return str(st.secrets.get(name,os.getenv(name,'')))
    except (FileNotFoundError,st.errors.StreamlitSecretNotFoundError):return os.getenv(name,'')


@st.cache_data(ttl=5,show_spinner=False)
def cloud_data(url,key,source):
    rows=Supabase(url,key).read(source)
    return validate_document({'schema_version':1,'source_id':source,'objects':rows,
        'fetched_at':datetime.now(timezone.utc).isoformat()})


@st.cache_data(show_spinner=False)
def replay_data():
    return bundled(ROOT/'dashboard/data/replay.json')


url,key,source=(config(n) for n in ('SUPABASE_URL','SUPABASE_PUBLISHABLE_KEY','CLOUD_SOURCE_ID'))
ready=bool(url and key and source)
st.sidebar.header('Explore o projeto')
mode=st.sidebar.radio('Fonte dos dados',['Nuvem · Supabase','Replay · histórico real'],index=0 if ready else 1)
page=st.sidebar.radio('Navegação',['Visão geral','Histórico de vibração','Sessões experimentais','Machine Learning experimental','Como funciona','Limitações e próximos passos'])
st.sidebar.caption('Somente leitura. Nenhum comando é enviado ao ESP32.')
st.sidebar.caption('Horários de Brasília (America/Sao_Paulo). Originais preservados em UTC.')
if mode.startswith('Replay'):
    play=st.sidebar.toggle('Reproduzir a cada 5 segundos',value=False)
    if st.sidebar.button('Reiniciar replay'):st.session_state['replay_cursor']=1
    st.sidebar.caption('O replay conserva os horários originais; não representa uma conexão com o sensor.')
else:play=False


def graph(rows,field,title,unit):
    fig=go.Figure(go.Scatter(x=[brazil_time(r['instante'],chart=True) for r in rows],y=[r[field] for r in rows],
        mode='lines+markers',line={'color':'#2463A6','width':2},marker={'size':4},
        customdata=[r['id'] for r in rows],hovertemplate='ID %{customdata}<br>%{x}<br>%{y}<extra></extra>',
        connectgaps=False))
    fig.update_layout(title=title,xaxis_title='Recepção original (horário de Brasília)',yaxis_title=unit,
        margin=dict(l=10,r=10,t=45,b=20),height=310,paper_bgcolor='#F8FAFC',plot_bgcolor='white')
    st.plotly_chart(fig,width='stretch')


@st.fragment(run_every='5s')
def monitor():
    historical=mode.startswith('Replay')
    if historical:
        st.info('REPLAY DE DADOS REAIS HISTÓRICOS — não são novas medições nem monitoramento ao vivo.')
        try:data=replay_data()
        except (OSError,ValueError,KeyError):
            st.error('Replay indisponível. Exporte dados reais antes da publicação.');return
        if play:
            cursor=st.session_state.get('replay_cursor',1)
            objects,total=replay_window(data,cursor)
            st.session_state['replay_cursor']=min(cursor+1,total)
            st.caption(f'Reprodução: {min(cursor,total)}/{total} registros históricos. Ao final, os horários não são reiniciados automaticamente.')
        else:objects=unpack(data)
        st.caption('Origem: SQLite da campanha física preservada. Dados de fixture não são utilizados.')
    else:
        if not ready:
            st.info('Nuvem não configurada. Escolha o replay histórico ou configure os secrets de leitura.');return
        try:
            data=cloud_data(url,key,source); objects=unpack(data)
            st.session_state['cloud_last_data']=data
            st.session_state['cloud_last_fetch']=data['fetched_at']
            st.success('Consulta ao Supabase concluída. Isso não comprova que o sensor esteja transmitindo agora.')
        except Exception:
            st.error('Consulta à nuvem indisponível. Credenciais e detalhes internos foram omitidos.')
            if 'cloud_last_data' not in st.session_state:return
            objects=unpack(st.session_state['cloud_last_data'])
            st.warning('Mostrando último resultado em cache — conexão não confirmada.')
        st.caption('Última consulta bem-sucedida: '+brazil_time(st.session_state.get('cloud_last_fetch')))
    measurements=objects['measurement']
    memberships={r['medicao_id']:r for r in objects['membership']}
    sessions={r['id']:r for r in objects['session']}
    if not measurements:
        st.info('Nenhuma medição real disponível nesta fonte.');return
    state,age=measurement_state(measurements)
    if historical:st.caption('Conexão com sensor: não se aplica ao replay. Último horário abaixo é histórico.')
    else:st.caption(f'Sensor: {state}. Idade da última recepção: {max(0,age):.0f} s.' if age is not None else state)
    st.caption('Última medição original: '+brazil_time(measurements[-1]['instante'])+f" · ID {measurements[-1]['id']}")
    if objects['status'] and not historical:
        status=objects['status'][0]
        st.caption(f"Sincronizador: última confirmação {brazil_time(status['last_success_at']) if status['last_success_at'] else 'ainda ausente'} · pendentes na verificação: {status['pending']} · com falha: {status['failed']} · verificado em {brazil_time(status['checked_at'])}")
    if page=='Visão geral':
        latest=measurements[-1]
        cols=st.columns(3)
        for col,field,label,unit in zip(cols,['rms','amplitude','pico_fft'],['RMS AC','Amplitude de pico','Frequência dominante'],['m/s²','m/s²','Hz']):
            v=latest[field];col.metric(label,'Indisponível' if v is None else f'{v:.4f} {unit}')
        st.caption('RMS e amplitude são grandezas diferentes. Frequência dominante não é RPM.')
        graph(measurements[-120:],'rms','Vibração nas últimas medições disponíveis','RMS (m/s²)')
        st.markdown('**Percurso dos dados:** MPU-6050 → ESP32/FFT → FastAPI → SQLite → sincronizador → Supabase → painel.')
    elif page=='Histórico de vibração':
        choices=['Todas']+list(sessions)
        selected=st.selectbox('Sessão do histórico',choices,key='history_session',
            format_func=lambda x: x if x=='Todas' else f"{sessions[x]['codigo']} · sessão {x} · campanha {sessions[x]['experimento_id'][:8]}")
        rows=[r for r in measurements if selected=='Todas' or memberships.get(r['id'],{}).get('sessao_id')==selected]
        for field,title,unit in [('rms','RMS ao longo do tempo','m/s²'),('amplitude','Amplitude ao longo do tempo','m/s²'),('pico_fft','Pico dominante ao longo do tempo','Hz')]:graph(rows,field,title,unit)
        st.dataframe(brazil_rows(rows),hide_index=True,width='stretch')
    elif page=='Sessões experimentais':
        st.caption('Mudanças de apoio e perturbações conhecidas; não são ensaios de falhas mecânicas.')
        summary=[];fig=go.Figure()
        for sid,sess in sessions.items():
            rows=[r for r in measurements if memberships.get(r['id'],{}).get('sessao_id')==sid]
            summary.append({'sessão':sess['codigo'],'estado':sess['estado'],'registros disponíveis':len(rows),'ID':sid,'campanha':sess['experimento_id']})
            fig.add_trace(go.Box(y=[r['rms'] for r in rows],name=f"{sess['codigo']} · {sid}",boxpoints='all',jitter=.2))
        st.dataframe(summary,hide_index=True,width='stretch')
        fig.update_layout(title='Distribuição de RMS por sessão',yaxis_title='m/s²',height=420)
        st.plotly_chart(fig,width='stretch')
        st.caption('Registros sem vínculo experimental continuam sem sessão; não são rotulados retroativamente.')
    elif page=='Machine Learning experimental':
        st.warning(ML_WARNING)
        models=objects['model'];scores=objects['score']
        if not models or not scores:st.info('Nenhum score histórico disponível. O painel não treina nem executa inferência.');return
        names={m['id']:m['variante'] for m in models}
        selected=st.selectbox('Modelo preservado',list(names),format_func=lambda x:names[x],key='model_select')
        byid={r['id']:r for r in measurements}
        rows=[{**r,'instante':byid[r['medicao_id']]['instante']} for r in scores if r['modelo_id']==selected and r['medicao_id'] in byid]
        rows.sort(key=lambda x:(x['instante'],x['medicao_id']))
        fig=go.Figure()
        for sid,sess in sessions.items():
            points=[r for r in rows if r['sessao_id']==sid]
            fig.add_trace(go.Scatter(x=[brazil_time(r['instante'],chart=True) for r in points],y=[r['score_decisao'] for r in points],mode='lines+markers',name=f"{sess['codigo']} · {sid}",customdata=[r['medicao_id'] for r in points],hovertemplate='ID %{customdata}<br>%{x}<br>%{y:.5f}<extra></extra>'))
        fig.add_hline(y=0,line_dash='dash',line_color='#183153')
        fig.update_layout(title='Scores históricos — menor significa mais incomum para o modelo',xaxis_title='Recepção original (horário de Brasília)',yaxis_title='decision_function',height=430)
        st.plotly_chart(fig,width='stretch')
        st.caption('Linha zero = limiar histórico preservado. Score não é probabilidade nem gravidade física. Treino somente NORMAL_01.')
        st.info('Na campanha auditada, ambos os modelos alertaram em 26% do treino e 100% de NORMAL_02 e RETORNO_01. Esses resultados não validam o detector para novas sessões normais.')
        st.dataframe(brazil_rows(rows),hide_index=True,width='stretch')
    elif page=='Como funciona':
        for title,text in [
            ('MPU-6050 · sentir','O acelerômetro mede aceleração no eixo X. Fixação e orientação influenciam a medição.'),
            ('ESP32 · adquirir','O microcontrolador lê 256 amostras a 500 Hz nominais e calcula a vibração real.'),
            ('FFT · separar frequências','Após remover a média e aplicar Hann, a FFT mostra componentes de frequência. Resolução nominal: 1,953125 Hz. Um pico não identifica sozinho uma falha.'),
            ('FastAPI · receber','Recebe POST autenticado por X-API-Key na rede local. O notebook não precisa ser exposto à internet.'),
            ('SQLite · preservar','Guarda medições e sessões localmente. A coleta funciona mesmo quando o envio à nuvem falha.'),
            ('Supabase · compartilhar','Recebe uma projeção pública mínima, via fila com reenvio e controle de duplicidade. O painel tem somente leitura.'),
            ('Isolation Forest · explorar','Aprende uma referência e atribui scores de observações incomuns. A validação atual não demonstrou generalização entre sessões normais.')]:
            st.subheader(title);st.write(text)
    else:
        st.markdown('''- Janelas de **0,512 s**, transmitidas a cada aproximadamente cinco segundos, podem perder eventos transitórios.
- Horários são de recepção no servidor; não há sincronização exata com o contato físico.
- A frequência de amostragem é nominal; há limitações de aliasing, montagem e calibração.
- O tacômetro continua desabilitado; não há RPM real confirmado.
- Scores históricos preservados; não há diagnóstico de falhas específicas.
- Próximos passos: repetibilidade normal, estabilização observada, novas sessões independentes e calibração externa.
- Nuvem é uma cópia para consulta. A fonte primária de aquisição continua sendo o SQLite local.''')


monitor()
st.divider()
st.caption('Projeto acadêmico de extensão · evidências físicas, transparência metodológica e acesso educacional.')
