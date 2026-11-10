"""Empacota allowlist para GitHub; bloqueia segredos conhecidos e arquivos privados."""
import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
DIRS=('backend','analytics','cloud_sync','dashboard','scripts','tests','supabase')
FILES=('README.md','.gitignore','.streamlit/config.toml','.streamlit/secrets.example.toml',
       'docs/DEPLOY_STATUS.md','docs/diagnostico_ml.md','docs/guia_nuvem.md',
       'docs/resultados_experimentais.md','docs/protocolo_experimental.md','docs/roteiro_bancada_ml.md',
       'docs/evidencias_cloud/validacao.json',
       'docs/evidencias_cloud/supabase_real.json',
       'docs/evidencias_cloud/deploy_publico.json','docs/evidencias_cloud/qrcode_dashboard.png',
       '.github/workflows/tests.yml','.env.example','.env.cloud.example')


def sensitive_values():
    values=[]
    p=ROOT/'.env'
    if p.exists():
        from dotenv import dotenv_values
        values += [v for k,v in dotenv_values(p).items() if any(x in k.upper() for x in ('KEY','PASSWORD','TOKEN','SECRET')) and v and len(v)>=8]
    p=ROOT/'firmware_fisico/secrets.h'
    if p.exists():
        values += [v for v in re.findall(r'\b(?:WIFI_SSID|WIFI_PASSWORD|API_KEY)\s*(?:\[\])?\s*(?:=|\s)\s*"([^"]+)"',p.read_text(encoding='utf-8')) if len(v)>=8]
    return values


def candidates():
    result=[ROOT/name for name in FILES if (ROOT/name).is_file()]
    result += list(ROOT.glob('requirements*.txt'))
    for directory in DIRS:
        result += [p for p in (ROOT/directory).rglob('*') if p.is_file() and
                   p.suffix in ('.py','.txt','.json','.sql','.md') and '__pycache__' not in p.parts]
    # Anexos diagnosticos publicos nao contem textos livres ou artefatos pickle.
    result += [p for p in (ROOT/'docs/evidencias_ml/diagnostico').glob('*') if p.is_file() and p.suffix in ('.json','.png','.svg')]
    return sorted(set(result))


def audit(files):
    secrets=sensitive_values();findings=[]
    for p in files:
        if p.suffix=='.png':continue
        raw=p.read_text(encoding='utf-8',errors='replace')
        if any(secret in raw for secret in secrets):findings.append(str(p.relative_to(ROOT)))
        if re.search(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',raw):findings.append(str(p.relative_to(ROOT)))
        # Valores literais de chaves privilegiadas, sem imprimir seus conteudos.
        if re.search(r'sb_secret_[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}',raw):findings.append(str(p.relative_to(ROOT)))
    if findings:raise ValueError('Possivel segredo: arquivos bloqueados: '+', '.join(sorted(set(findings))))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--saida',type=Path)
    ap.add_argument('--check',action='store_true')
    args=ap.parse_args();files=candidates();audit(files)
    if args.check:print('Allowlist auditada sem valores de segredos conhecidos:',len(files),'arquivos.');return
    output=args.saida or ROOT/'.marco3_local'/('publicacao_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    if output.exists():sys.exit('Destino existente preservado; escolha pasta nova.')
    output.mkdir(parents=True)
    hashes={}
    for p in files:
        name=p.relative_to(ROOT);dest=output/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        hashes[name.as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    (output/'PUBLICATION_MANIFEST.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print('Pacote seguro preparado:',len(files),'arquivos. Sem .env, secrets.h, SQLite, outbox, backups ou pickle.')


if __name__=='__main__':main()
