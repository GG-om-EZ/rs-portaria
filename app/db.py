"""Conexão SQLite e schema. Dinheiro sempre em centavos (INTEGER)."""
import os
import sqlite3
from pathlib import Path

# DDL compartilhada entre o CREATE inicial e o rebuild da migração (v1.1)
_LINHAS_CUSTO_DDL = """(
    id INTEGER PRIMARY KEY,
    proposta_id INTEGER NOT NULL REFERENCES propostas (id) ON DELETE CASCADE,
    funcao_id INTEGER REFERENCES funcoes (id),
    descricao TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT 'mao_de_obra'
        CHECK (categoria IN ('mao_de_obra', 'acessorio', 'derivada', 'manual')),
    quantidade INTEGER NOT NULL DEFAULT 1,
    valor_sugerido_centavos INTEGER NOT NULL,
    valor_final_centavos INTEGER NOT NULL,
    sobrescrito INTEGER NOT NULL DEFAULT 0,
    ordem INTEGER NOT NULL DEFAULT 1
)"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY,
    razao_social TEXT NOT NULL,
    cnpj TEXT NOT NULL UNIQUE,
    endereco TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    telefone TEXT NOT NULL DEFAULT '',
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS parametros (
    id INTEGER PRIMARY KEY,
    chave TEXT NOT NULL,
    valor TEXT NOT NULL,
    vigencia_inicio TEXT NOT NULL,  -- data ISO; vigente = maior <= hoje
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_parametros_chave ON parametros (chave, vigencia_inicio);

CREATE TABLE IF NOT EXISTS funcoes (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('continuo', 'evento')),
    valor_base_centavos INTEGER NOT NULL,  -- piso mensal (continuo) ou diária (evento)
    aplica_noturno INTEGER NOT NULL DEFAULT 0,
    ativa INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS propostas (
    id INTEGER PRIMARY KEY,
    tipo TEXT NOT NULL CHECK (tipo IN ('continuo', 'evento')),
    status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'emitida')),
    numero TEXT,
    cliente_id INTEGER REFERENCES clientes (id),
    dados_json TEXT NOT NULL DEFAULT '{}',
    snapshot_json TEXT,
    pdf_arquivado INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    emitida_em TEXT
);

CREATE TABLE IF NOT EXISTS linhas_custo """ + _LINHAS_CUSTO_DDL + """;

CREATE TABLE IF NOT EXISTS sequencia_numeracao (
    ano INTEGER PRIMARY KEY,
    ultimo INTEGER NOT NULL
);
"""


def db_path() -> Path:
    return Path(os.environ.get("RSP_DB", "data/rsportaria.db"))


def get_conn(path=None) -> sqlite3.Connection:
    p = Path(path) if path else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False é necessário em produção: conn_dep (generator sync)
    # roda no threadpool do Starlette, enquanto endpoints async rodam no event loop -
    # a mesma conexão cruza threads dentro de um request. Seguro porque cada conexão
    # é por-request e usada sequencialmente (nunca de forma concorrente).
    conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrar_categoria_manual(conn: sqlite3.Connection) -> None:
    """Bancos pré-v1.1 têm CHECK de categoria sem 'manual'. SQLite não altera
    CHECK - rebuild da tabela preservando os dados."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'linhas_custo'"
    ).fetchone()
    if row is None or "'manual'" in row["sql"]:
        return
    conn.commit()  # PRAGMA foreign_keys não muda dentro de transação aberta
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("CREATE TABLE linhas_custo_nova " + _LINHAS_CUSTO_DDL)
        conn.execute("INSERT INTO linhas_custo_nova SELECT * FROM linhas_custo")
        conn.execute("DROP TABLE linhas_custo")
        conn.execute("ALTER TABLE linhas_custo_nova RENAME TO linhas_custo")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrar_categoria_manual(conn)
    conn.commit()


def conn_dep():
    """Dependency do FastAPI: uma conexão por request."""
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()
