"""Esquema SQL da tabela de medicoes."""

CENARIOS = {0: "normal", 1: "desbalanceamento", 2: "desalinhamento"}

TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS medicoes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    instante      TEXT    NOT NULL,            -- UTC, ISO 8601
    dispositivo   TEXT    NOT NULL,
    rpm           REAL,
    frequencia_1x REAL,
    pico_fft      REAL    NOT NULL,
    amplitude     REAL    NOT NULL,
    cenario       INTEGER,
    origem        TEXT    NOT NULL,
    rms           REAL,
    atrasos       INTEGER
);
"""
INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_medicoes_instante ON medicoes (instante DESC)",
    "CREATE INDEX IF NOT EXISTS idx_medicoes_dispositivo ON medicoes (dispositivo, instante DESC)",
)
SCHEMA = TABLE_SCHEMA + ";\n".join(INDEXES) + ";\n"

INSERT = """
INSERT INTO medicoes (instante, dispositivo, rpm, frequencia_1x, pico_fft, amplitude, cenario, origem,
                      rms, atrasos)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
