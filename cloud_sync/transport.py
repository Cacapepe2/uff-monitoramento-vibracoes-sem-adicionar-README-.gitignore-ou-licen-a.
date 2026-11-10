"""Supabase REST: escritor Auth restrito e leitor anonimo somente leitura; TLS obrigatorio."""
import base64
import json
import re
import time
from urllib.parse import urlparse

import requests


def safe_config(url, key):
    p = urlparse(url)
    if p.scheme != 'https' or not re.fullmatch(r'[a-z0-9-]+\.supabase\.co',p.hostname or '') or p.path not in ('','/') or p.query or p.fragment or p.username or p.port:
        raise ValueError('Use somente a URL HTTPS oficial do projeto Supabase')
    if key.startswith('sb_secret_'):
        raise ValueError('Chave privilegiada proibida; use publishable/anon')
    if key.startswith('eyJ'):
        try:
            payload=json.loads(base64.urlsafe_b64decode(key.split('.')[1]+'=='))
        except Exception:
            raise ValueError('Chave anon invalida') from None
        if payload.get('role') != 'anon':
            raise ValueError('JWT privilegiado proibido')
    elif not key.startswith('sb_publishable_'):
        raise ValueError('Chave publishable/anon necessaria')
    return url.rstrip('/')


class Supabase:
    def __init__(self,url,key,session=None):
        self.url=safe_config(url,key)
        self.session=session or requests.Session()
        self.session.trust_env=False
        self.headers={'apikey':key,'Content-Type':'application/json'}
        self.token=None; self.expires=0

    def login(self,email,password):
        r=self.session.post(self.url+'/auth/v1/token?grant_type=password',headers=self.headers,
                            json={'email':email,'password':password},timeout=(5,15),allow_redirects=False)
        if r.status_code != 200:
            raise RuntimeError('Autenticacao do sincronizador recusada; detalhes sensiveis omitidos')
        data=r.json(); self.token=data['access_token'];self.expires=time.time()+int(data['expires_in'])-60

    def send(self,source_id,batch):
        if not self.token or time.time()>=self.expires:
            raise RuntimeError('Sessao Auth do sincronizador expirada')
        objects=[{'kind':r['kind'],'entity_id':r['entity_id'],'payload':json.loads(r['payload']),
                  'content_hash':r['hash'],'revision':r['revision']} for r in batch]
        r=self.session.post(self.url+'/rest/v1/rpc/vibration_sync_batch',
            headers={**self.headers,'Authorization':'Bearer '+self.token},
            json={'p_source':source_id,'p_items':objects},timeout=(5,30),allow_redirects=False)
        if r.status_code==401:
            self.token=None
        if r.status_code != 200 or r.json()!=len(batch):
            raise RuntimeError('Lote nao confirmado pelo Supabase; sera reenviado')

    def read(self,source_id,max_rows=20000,since=None):
        result=[]
        for offset in range(0,max_rows,1000):
            params={'source_id':'eq.'+source_id,'select':'kind,entity_id,payload,received_at',
                    'order':'kind,entity_id' if since is None else 'received_at,kind,entity_id',
                    'offset':offset,'limit':min(1000,max_rows-offset)}
            if since is not None:
                params['received_at']='gte.'+since
            r=self.session.get(self.url+'/rest/v1/vibration_objects',headers=self.headers,
                params=params,
                timeout=(5,15),allow_redirects=False)
            if r.status_code!=200:
                raise RuntimeError('Leitura da nuvem indisponivel; nenhuma credencial exibida')
            page=r.json();result.extend(page)
            if len(page)<1000:
                return result
        raise RuntimeError('Limite de leitura atingido; filtre ou arquive a telemetria antes de continuar')
