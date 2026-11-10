"""Controle de bancada via API autenticada; nunca cria medicoes de exemplo."""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
POINTER = ROOT / '.marco3_local/experimento_atual.json'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url', default='http://127.0.0.1:8000')
    ap.add_argument('--experimento', help='UUID; padrao: ultimo planejamento criado por este cliente')
    subs = ap.add_subparsers(dest='action', required=True)
    plan = subs.add_parser('planejar')
    plan.add_argument('--nome', required=True)
    plan.add_argument('--dispositivo', default='esp32-fisico-01')
    plan.add_argument('--observacoes', default='')
    subs.add_parser('status')
    start = subs.add_parser('iniciar')
    start.add_argument('codigo')
    start.add_argument('--condicao', required=True)
    start.add_argument('--observacoes', default='')
    start.add_argument('--espera-s', type=int, default=10)
    end = subs.add_parser('encerrar')
    end.add_argument('codigo')
    end.add_argument('--observacoes', default='')
    event = subs.add_parser('evento-iniciar')
    event.add_argument('--descricao', required=True)
    event.add_argument('--observacoes', default='')
    subs.add_parser('evento-encerrar')
    follow = subs.add_parser('acompanhar')
    follow.add_argument('codigo')
    follow.add_argument('--timeout-s', type=int, default=900)
    subs.add_parser('treinar')
    evaluate = subs.add_parser('avaliar')
    evaluate.add_argument('--comparacao')
    evaluate.add_argument('--saida', default=str(ROOT/'.marco3_local/relatorio_experimental.json'))
    evaluate.add_argument('--html', help='Exportar graficos offline, sem publicar na internet')
    args = ap.parse_args()
    load_dotenv(ROOT/'.env')
    key = os.getenv('API_KEY', '')
    if not key:
        sys.exit('API_KEY ausente. Configure o ambiente/.env; o cliente nao envia sem autenticacao.')
    client = requests.Session()
    client.trust_env = False
    client.headers['X-API-Key'] = key

    def request(method, path, body=None):
        try:
            response = client.request(method, args.url.rstrip('/')+path, json=body, timeout=60)
        except requests.RequestException:
            sys.exit('API indisponivel. Confira o servico local e a conectividade; endereco omitido.')
        if not response.ok:
            try:
                detail = response.json()
            except ValueError:
                detail = {'detail': 'Resposta sem JSON'}
            text = json.dumps(detail, ensure_ascii=True).replace(key, '[OMITIDO]')
            text = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '[IP_OMITIDO]', text)
            sys.exit(f'HTTP {response.status_code}: {text}')
        return response.json()

    if args.action == 'planejar':
        result = request('POST', '/experimentos', {'nome': args.nome, 'dispositivo': args.dispositivo,
                                                  'observacoes': args.observacoes})
        POINTER.parent.mkdir(exist_ok=True, parents=True)
        POINTER.write_text(json.dumps({'experimento_id': result['id']}), encoding='utf-8')
        print('Planejamento criado, sem medicoes e sem iniciar coleta. Experimento:', result['id'])
        for session in result['sessoes']:
            print(session['codigo'], '| id=', session['id'], '| estado=', session['estado'])
        return
    eid = args.experimento
    if not eid and POINTER.exists():
        eid = json.loads(POINTER.read_text(encoding='utf-8'))['experimento_id']
    if not eid:
        sys.exit('Nenhum experimento selecionado. Execute planejar ou informe --experimento UUID.')
    experiment = request('GET', f'/experimentos/{eid}')

    def session(code):
        found = next((s for s in experiment['sessoes'] if s['codigo'] == code), None)
        if found is None:
            sys.exit('Codigo de sessao nao encontrado neste experimento.')
        return found

    if args.action == 'status':
        print('Experimento:', eid)
        for s in experiment['sessoes']:
            print(f"{s['codigo']:12} {s['estado']:10} elegiveis={s['registros_elegiveis']} "
                  f"recebidos={s['registros_recebidos']} excluidos={s['registros_excluidos']} "
                  f"meta={s['meta_registros']} minimo={s['minimo_avaliacao']}")
    elif args.action == 'iniciar':
        s = session(args.codigo)
        result = request('POST', f"/sessoes/{s['id']}/iniciar", {'condicao': args.condicao,
            'observacoes': args.observacoes, 'espera_estabilizacao_s': args.espera_s})
        print('Sessao iniciada:', result['codigo'], '| id=', result['id'],
              '| coleta por recepcao UTC a partir de:', result['coleta_a_partir'])
    elif args.action == 'encerrar':
        s = session(args.codigo)
        result = request('POST', f"/sessoes/{s['id']}/encerrar", {'observacoes': args.observacoes})
        print('Sessao encerrada:', result['codigo'], '| elegiveis=', result['registros_elegiveis'],
              '| dados suficientes=', result['dados_suficientes'])
    elif args.action == 'evento-iniciar':
        s = session('TOQUE_01')
        result = request('POST', f"/sessoes/{s['id']}/eventos", {'descricao': args.descricao,
                                                                 'observacoes': args.observacoes})
        print('Evento iniciado:', result['id'], '| UTC:', result['inicio'])
    elif args.action == 'evento-encerrar':
        opened = next((e for e in session('TOQUE_01')['eventos'] if e['fim'] is None), None)
        if not opened:
            sys.exit('Nenhum evento aberto na sessao TOQUE_01.')
        result = request('POST', f"/eventos/{opened['id']}/encerrar")
        print('Evento encerrado:', result['id'], '| UTC:', result['fim'])
    elif args.action == 'acompanhar':
        sid = session(args.codigo)['id']
        deadline, previous = time.monotonic()+args.timeout_s, None
        while time.monotonic() < deadline:
            data = request('GET', f'/sessoes/{sid}')
            current = (data['estado'], data['registros_elegiveis'], data['registros_excluidos'])
            if current != previous:
                print(data['codigo'], '| estado, elegiveis, excluidos:', current, flush=True)
                previous = current
            if data['estado'] == 'encerrada':
                return
            time.sleep(2)
        sys.exit('Tempo de acompanhamento encerrado; a sessao permanece no estado informado pela API.')
    elif args.action == 'treinar':
        result = request('POST', f'/experimentos/{eid}/modelos')
        print('Comparacao criada:', result['comparacao_id'])
        for model in result['modelos']:
            print(model['variante'], '| modelo=', model['id'], '| registros de treino=', len(model['ids_treino']))
    elif args.action == 'avaliar':
        report = request('POST', f'/experimentos/{eid}/avaliar', {'comparacao_id': args.comparacao})
        path = Path(args.saida)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        print(report['status'], '|', report['mensagem'])
        for model in report['modelos']:
            for summary in model['sessoes']:
                rate = summary['taxa_alertas']
                text = f'{rate:.1%}' if rate is not None else 'DADOS INSUFICIENTES'
                print(model['variante'], summary['codigo'], f"n={summary['n']}", text)
        if args.html:
            from analytics.visualization import write_html
            write_html(report, args.html)
            print('Graficos HTML locais exportados.')
        print('Relatorio JSON salvo; nenhuma publicacao ou deploy foi realizado.')


if __name__ == '__main__':
    main()
