import os
import sqlite3
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path

from .models import INDEXES, TABLE_SCHEMA
from .experiment_schema import DDL as EXPERIMENT_DDL

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "dados" / "medicoes.db"


def resolve_db_path(path=None) -> Path:
    p = Path(path or os.getenv("DB_PATH") or DEFAULT_DB)
    if not p.is_absolute():
        p = ROOT / p
    return p


def connect(path) -> sqlite3.Connection:
    # FastAPI pode criar, usar e fechar a dependencia em threads distintas.
    # Cada requisicao continua com sua propria conexao e transacao.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        columns = conn.execute("PRAGMA table_info(medicoes)").fetchall()
        legacy = bool(columns) and _needs_migration(columns)
        experimental_missing = not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='experimentos'"
        ).fetchone()
        if columns and (legacy or experimental_missing):
            # Backup pela API SQLite: consistente inclusive se houver WAL.
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            stage = 'marco3' if legacy else 'experimentos'
            backup_path = Path(str(path) + f".pre-{stage}-{stamp}.bak")
            with closing(sqlite3.connect(backup_path)) as backup:
                conn.backup(backup)
        # Nao usar executescript: ele faria COMMIT implicito antes da migracao.
        conn.execute("BEGIN IMMEDIATE")
        columns = conn.execute("PRAGMA table_info(medicoes)").fetchall()
        if not columns:
            conn.execute(TABLE_SCHEMA)
        elif _needs_migration(columns):
            _migrate_marco3(conn, columns)
        for index in INDEXES:
            conn.execute(index)
        for statement in EXPERIMENT_DDL:
            conn.execute(statement)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _needs_migration(columns) -> bool:
    info = {c["name"]: c for c in columns}
    return (not {"rms", "atrasos"}.issubset(info)
            or any(info[name]["notnull"] for name in ("rpm", "frequencia_1x", "cenario")))


def _migrate_marco3(conn, columns) -> None:
    """SQLite nao remove NOT NULL com ALTER COLUMN; recria dentro da transacao."""
    old_names = [c["name"] for c in columns]
    supported = {"id", "instante", "dispositivo", "rpm", "frequencia_1x", "pico_fft",
                 "amplitude", "cenario", "origem", "rms", "atrasos"}
    if set(old_names) - supported:
        raise RuntimeError("Banco com colunas desconhecidas; migracao cancelada para preservar dados")
    objects = conn.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name='medicoes' "
        "AND type IN ('index', 'trigger') AND sql IS NOT NULL"
    ).fetchall()
    seq = conn.execute("SELECT seq FROM sqlite_sequence WHERE name='medicoes'").fetchone()
    conn.execute(TABLE_SCHEMA.replace("IF NOT EXISTS medicoes", "medicoes_marco3"))
    names = ", ".join(f'"{name}"' for name in old_names)
    conn.execute(f"INSERT INTO medicoes_marco3 ({names}) SELECT {names} FROM medicoes")
    conn.execute("DROP TABLE medicoes")
    conn.execute("ALTER TABLE medicoes_marco3 RENAME TO medicoes")
    if seq:
        # Preserva inclusive IDs de registros que ja foram excluidos.
        conn.execute("DELETE FROM sqlite_sequence WHERE name='medicoes'")
        conn.execute("INSERT INTO sqlite_sequence(name, seq) VALUES ('medicoes', ?)", (seq[0],))
    for obj in objects:
        conn.execute(obj["sql"])
