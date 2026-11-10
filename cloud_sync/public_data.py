"""Contrato publico por allowlist: sem observacoes livres, credenciais ou pickle."""
import json
import sqlite3
from pathlib import Path

FIELDS = {
    'measurement': ('id','instante','pico_fft','amplitude','rms','atrasos','origem'),
    'session': ('id','experimento_id','codigo','estado','inicio','fim','meta_registros'),
    'membership': ('medicao_id','sessao_id','elegivel','motivo_exclusao'),
    'event': ('id','sessao_id','inicio','fim'),
    'model': ('id','comparacao_id','experimento_id','sessao_treino_id','variante','criado_em','dados_sha256','artefato_sha256'),
    'score': ('modelo_id','medicao_id','sessao_id','papel','score_bruto','score_decisao','alerta','calculado_em'),
    'status': ('last_success_at','pending','failed','checked_at'),
}
ML_WARNING = 'Modelo experimental — validação pendente. Os alertas ainda não demonstraram generalização adequada entre sessões normais.'


def project(kind, row):
    return {key: row[key] for key in FIELDS[kind]}


def read_objects(path, device='esp32-fisico-01'):
    """Snapshot consistente somente leitura; historico sem sessao permanece sem rotulo."""
    conn = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('BEGIN')
        rows = conn.execute("SELECT * FROM medicoes WHERE origem='real' AND dispositivo=? ORDER BY id", (device,)).fetchall()
        mids = {r['id'] for r in rows}
        members = [r for r in conn.execute('SELECT * FROM medicoes_sessoes') if r['medicao_id'] in mids]
        sids = {r['sessao_id'] for r in members}
        sessions = [r for r in conn.execute('SELECT * FROM sessoes_experimentais WHERE dispositivo=?', (device,))]
        sids.update(r['id'] for r in sessions)
        models = [r for r in conn.execute('SELECT * FROM modelos_ml') if r['sessao_treino_id'] in sids]
        modelids = {r['id'] for r in models}
        result = [('measurement',str(r['id']),project('measurement',r)) for r in rows]
        result += [('session',str(r['id']),project('session',r)) for r in sessions]
        result += [('membership',str(r['medicao_id']),project('membership',r)) for r in members]
        result += [('event',str(r['id']),project('event',r)) for r in conn.execute('SELECT * FROM eventos_experimentais') if r['sessao_id'] in sids]
        result += [('model',r['id'],project('model',r)) for r in models]
        result += [('score',r['modelo_id']+':'+str(r['medicao_id']),project('score',r))
                   for r in conn.execute('SELECT * FROM ml_scores') if r['modelo_id'] in modelids and r['medicao_id'] in mids]
        return result
    finally:
        conn.close()


def document(objects, source_id, generated_at):
    return {'schema_version': 1, 'source_id': source_id, 'exported_at': generated_at,
            'historical': True, 'ml_warning': ML_WARNING,
            'objects': [{'kind':k,'entity_id':i,'payload':p} for k,i,p in objects]}


def validate_document(data):
    if data.get('schema_version') != 1 or not isinstance(data.get('objects'),list):
        raise ValueError('Formato publico invalido')
    for item in data['objects']:
        if item['kind'] not in FIELDS or set(item['payload']) != set(FIELDS[item['kind']]):
            raise ValueError('Objeto fora do contrato publico')
    json.dumps(data, allow_nan=False)
    return data
