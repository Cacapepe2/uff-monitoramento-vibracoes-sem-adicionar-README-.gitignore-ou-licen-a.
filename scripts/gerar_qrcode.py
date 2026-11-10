"""Gera QR somente de URL publica fornecida e com resposta HTTPS verificavel."""
import argparse
from pathlib import Path
from urllib.parse import urlparse, urljoin
import requests


def validate_url(url):
    p=urlparse(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError('URL HTTPS publica sem credenciais ou parametros necessaria')
    if not p.hostname.endswith('.streamlit.app'):
        raise ValueError('Use a URL real do dashboard Streamlit Community Cloud')
    return url


def verify_public_url(url):
    """Aceita somente o bootstrap HTTPS oficial e retorno ao app original."""
    url=validate_url(url)
    original=urlparse(url).hostname
    current=url
    with requests.Session() as session:
        session.trust_env=False
        for _ in range(8):
            parsed=urlparse(current)
            if (parsed.scheme!='https' or parsed.hostname not in (original,'share.streamlit.io')
                    or parsed.username or parsed.password or parsed.port not in (None,443)):
                raise ValueError('Redirecionamento fora do destino oficial')
            response=session.get(current,timeout=(5,20),allow_redirects=False)
            if response.status_code in (301,302,303,307,308):
                location=response.headers.get('Location')
                if not location:raise ValueError('Redirecionamento sem destino')
                current=urljoin(current,location)
                continue
            if response.status_code==200 and parsed.hostname==original:
                return
            raise ValueError('URL do app nao confirmada com HTTP 200')
    raise ValueError('Limite de redirecionamentos do app excedido')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('url');ap.add_argument('--saida',type=Path,default=Path('relatorios/qrcode_dashboard.png'))
    args=ap.parse_args();url=validate_url(args.url)
    verify_public_url(url)
    import qrcode
    args.saida.parent.mkdir(parents=True,exist_ok=True);qrcode.make(url).save(args.saida)
    print('QR gerado a partir da URL fornecida, verificada com HTTP 200. Conferir conteudo do app no navegador antes de distribuir.')
