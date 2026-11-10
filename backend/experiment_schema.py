"""Extensao aditiva: nenhuma coluna/linha antiga de medicoes e reclassificada."""

DDL = (
    """CREATE TABLE IF NOT EXISTS experimentos (
        id TEXT PRIMARY KEY, nome TEXT NOT NULL, dispositivo TEXT NOT NULL,
        protocolo TEXT NOT NULL, criado_em TEXT NOT NULL, observacoes TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS sessoes_experimentais (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experimento_id TEXT NOT NULL REFERENCES experimentos(id),
        codigo TEXT NOT NULL CHECK(codigo IN
          ('NORMAL_01','NORMAL_02','BORRACHA_01','MADEIRA_01','TOQUE_01','RETORNO_01')),
        dispositivo TEXT NOT NULL, condicao_planejada TEXT NOT NULL,
        condicao_observada TEXT, observacoes TEXT NOT NULL DEFAULT '',
        estado TEXT NOT NULL DEFAULT 'planejada' CHECK(estado IN ('planejada','ativa','encerrada')),
        meta_registros INTEGER, minimo_avaliacao INTEGER NOT NULL,
        criada_em TEXT NOT NULL, inicio TEXT, coleta_a_partir TEXT, fim TEXT,
        marco_inicio_id INTEGER, espera_estabilizacao_s INTEGER,
        UNIQUE(experimento_id,codigo))""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uma_sessao_ativa_por_dispositivo
        ON sessoes_experimentais(dispositivo) WHERE estado='ativa'""",
    """CREATE TABLE IF NOT EXISTS medicoes_sessoes (
        medicao_id INTEGER PRIMARY KEY REFERENCES medicoes(id),
        sessao_id INTEGER NOT NULL REFERENCES sessoes_experimentais(id),
        associada_em TEXT NOT NULL, elegivel INTEGER NOT NULL CHECK(elegivel IN (0,1)),
        motivo_exclusao TEXT, UNIQUE(medicao_id,sessao_id))""",
    "CREATE INDEX IF NOT EXISTS idx_medicoes_sessao ON medicoes_sessoes(sessao_id,medicao_id)",
    """CREATE TABLE IF NOT EXISTS auditoria_sessoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sessao_id INTEGER NOT NULL REFERENCES sessoes_experimentais(id),
        acao TEXT NOT NULL, instante TEXT NOT NULL, detalhes TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS eventos_experimentais (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sessao_id INTEGER NOT NULL REFERENCES sessoes_experimentais(id),
        descricao TEXT NOT NULL, inicio TEXT NOT NULL, fim TEXT, observacoes TEXT NOT NULL,
        CHECK(fim IS NULL OR fim>=inicio))""",
    """CREATE UNIQUE INDEX IF NOT EXISTS um_evento_aberto_por_sessao
        ON eventos_experimentais(sessao_id) WHERE fim IS NULL""",
    """CREATE TABLE IF NOT EXISTS modelos_ml (
        id TEXT PRIMARY KEY, comparacao_id TEXT NOT NULL,
        experimento_id TEXT NOT NULL REFERENCES experimentos(id),
        sessao_treino_id INTEGER NOT NULL REFERENCES sessoes_experimentais(id),
        variante TEXT NOT NULL, features_json TEXT NOT NULL, parametros_json TEXT NOT NULL,
        ambiente_json TEXT NOT NULL, dados_sha256 TEXT NOT NULL, artefato_sha256 TEXT NOT NULL,
        artefato BLOB NOT NULL, criado_em TEXT NOT NULL,
        UNIQUE(comparacao_id,variante))""",
    """CREATE TABLE IF NOT EXISTS ml_treino (
        modelo_id TEXT NOT NULL REFERENCES modelos_ml(id),
        medicao_id INTEGER NOT NULL REFERENCES medicoes_sessoes(medicao_id),
        PRIMARY KEY(modelo_id,medicao_id))""",
    """CREATE TABLE IF NOT EXISTS ml_scores (
        modelo_id TEXT NOT NULL REFERENCES modelos_ml(id),
        medicao_id INTEGER NOT NULL, sessao_id INTEGER NOT NULL,
        papel TEXT NOT NULL CHECK(papel IN ('treinamento','avaliacao')),
        score_bruto REAL NOT NULL, score_decisao REAL NOT NULL,
        alerta INTEGER NOT NULL CHECK(alerta IN (0,1)), calculado_em TEXT NOT NULL,
        PRIMARY KEY(modelo_id,medicao_id),
        FOREIGN KEY(medicao_id,sessao_id) REFERENCES medicoes_sessoes(medicao_id,sessao_id))""",
    """CREATE TRIGGER IF NOT EXISTS validar_associacao_experimental
        BEFORE INSERT ON medicoes_sessoes BEGIN
          SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM medicoes m JOIN sessoes_experimentais s ON s.id=new.sessao_id
            WHERE m.id=new.medicao_id AND m.origem='real' AND m.dispositivo=s.dispositivo
            AND s.estado='ativa' AND m.id>s.marco_inicio_id
            AND m.instante>=s.coleta_a_partir
          ) THEN RAISE(ABORT,'associacao fora da sessao ativa ou retroativa') END;
        END""",
    """CREATE TRIGGER IF NOT EXISTS associacao_experimental_imutavel
        BEFORE UPDATE ON medicoes_sessoes BEGIN
          SELECT RAISE(ABORT,'associacao experimental imutavel'); END""",
    """CREATE TRIGGER IF NOT EXISTS preservar_associacao_experimental
        BEFORE DELETE ON medicoes_sessoes BEGIN
          SELECT RAISE(ABORT,'associacao experimental imutavel'); END""",
    """CREATE TRIGGER IF NOT EXISTS preservar_medicao_experimental_update
        BEFORE UPDATE ON medicoes WHEN EXISTS
          (SELECT 1 FROM medicoes_sessoes WHERE medicao_id=old.id)
        BEGIN SELECT RAISE(ABORT,'medicao experimental imutavel'); END""",
    """CREATE TRIGGER IF NOT EXISTS preservar_medicao_experimental_delete
        BEFORE DELETE ON medicoes WHEN EXISTS
          (SELECT 1 FROM medicoes_sessoes WHERE medicao_id=old.id)
        BEGIN SELECT RAISE(ABORT,'medicao experimental imutavel'); END""",
    """CREATE TRIGGER IF NOT EXISTS treino_somente_normal01
        BEFORE INSERT ON ml_treino BEGIN
          SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM modelos_ml ml JOIN medicoes_sessoes a ON a.medicao_id=new.medicao_id
            JOIN sessoes_experimentais s ON s.id=a.sessao_id
            WHERE ml.id=new.modelo_id AND s.codigo='NORMAL_01' AND a.elegivel=1
            AND s.id=ml.sessao_treino_id AND s.experimento_id=ml.experimento_id
            AND s.estado='encerrada'
          ) THEN RAISE(ABORT,'treino restrito a NORMAL_01 elegivel do experimento') END;
        END""",
    """CREATE TRIGGER IF NOT EXISTS validar_rastreabilidade_score
        BEFORE INSERT ON ml_scores BEGIN
          SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM modelos_ml ml JOIN medicoes_sessoes a ON a.medicao_id=new.medicao_id
            JOIN sessoes_experimentais s ON s.id=a.sessao_id
            WHERE ml.id=new.modelo_id AND s.id=new.sessao_id AND a.elegivel=1
            AND s.experimento_id=ml.experimento_id AND s.estado='encerrada'
            AND ((new.papel='treinamento' AND s.id=ml.sessao_treino_id
              AND EXISTS(SELECT 1 FROM ml_treino t WHERE t.modelo_id=ml.id AND t.medicao_id=new.medicao_id))
              OR (new.papel='avaliacao' AND s.id!=ml.sessao_treino_id))
          ) THEN RAISE(ABORT,'score sem rastreabilidade compativel') END;
        END""",
    """CREATE TRIGGER IF NOT EXISTS score_experimental_imutavel
        BEFORE UPDATE ON ml_scores BEGIN SELECT RAISE(ABORT,'score imutavel'); END""",
    """CREATE TRIGGER IF NOT EXISTS preservar_score_experimental
        BEFORE DELETE ON ml_scores BEGIN SELECT RAISE(ABORT,'score imutavel'); END""",
)
