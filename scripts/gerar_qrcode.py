"""Gera QR somente de URL publica fornecida e com resposta HTTPS verificavel."""
import argparse
import ipaddress
from pathlib import Path
from urllib.parse import urlparse
import requests


def validate_url(url):
    p=urlparse(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError('URL HTTPS publica sem credenciais ou parametros necessaria')
    if not p.hostname.endswith('.streamlit.app'):
        raise ValueError('Use a URL real do dashboard Streamlit Community Cloud')
    return url


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('url');ap.add_argument('--saida',type=Path,default=Path('relatorios/qrcode_dashboard.png'))
    args=ap.parse_args();url=validate_url(args.url)
    response=requests.get(url,timeout=(5,20),allow_redirects=False)
    if response.status_code!=200:raise SystemExit('URL nao confirmada com HTTP 200. QR nao gerado.')
    import qrcode
    args.saida.parent.mkdir(parents=True,exist_ok=True);qrcode.make(url).save(args.saida)
    print('QR gerado a partir da URL fornecida, verificada com HTTP 200. Conferir conteudo do app no navegador antes de distribuir.')
