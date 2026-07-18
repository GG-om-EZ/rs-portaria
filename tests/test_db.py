import sqlite3

import pytest

from app import db as dbmod

# Definição de linhas_custo anterior à v1.1, sem 'manual' no CHECK de categoria
_LINHAS_CUSTO_PRE_V11 = """
CREATE TABLE linhas_custo (
    id INTEGER PRIMARY KEY,
    proposta_id INTEGER NOT NULL REFERENCES propostas (id) ON DELETE CASCADE,
    funcao_id INTEGER REFERENCES funcoes (id),
    descricao TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT 'mao_de_obra'
        CHECK (categoria IN ('mao_de_obra', 'acessorio', 'derivada')),
    quantidade INTEGER NOT NULL DEFAULT 1,
    valor_sugerido_centavos INTEGER NOT NULL,
    valor_final_centavos INTEGER NOT NULL,
    sobrescrito INTEGER NOT NULL DEFAULT 0,
    ordem INTEGER NOT NULL DEFAULT 1
);
"""

_INSERT_LINHA = (
    "INSERT INTO linhas_custo (proposta_id, descricao, categoria, quantidade,"
    " valor_sugerido_centavos, valor_final_centavos, sobrescrito, ordem)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)


def test_schema_cria_tabelas(conn):
    nomes = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "clientes", "parametros", "funcoes",
        "propostas", "linhas_custo", "sequencia_numeracao",
    } <= nomes


def test_foreign_keys_ativas(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_categoria_manual_aceita_em_banco_novo(conn):
    dbmod.init_db(conn)  # segunda chamada deve ser inócua
    pid = conn.execute("INSERT INTO propostas (tipo) VALUES ('continuo')").lastrowid
    conn.execute(_INSERT_LINHA, (pid, "Operacional", "manual", 1, 20800, 20800, 0, 4))
    conn.commit()


def test_migra_banco_pre_v11_para_aceitar_manual(tmp_path):
    c = dbmod.get_conn(tmp_path / "antigo.db")
    dbmod.init_db(c)
    # Regride linhas_custo para o schema pré-v1.1 e povoa com uma linha sobrescrita
    c.executescript("DROP TABLE linhas_custo;" + _LINHAS_CUSTO_PRE_V11)
    pid = c.execute("INSERT INTO propostas (tipo) VALUES ('continuo')").lastrowid
    c.execute(_INSERT_LINHA, (pid, "Porteiro diurno", "mao_de_obra", 2, 160000, 155000, 1, 1))
    c.commit()
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(_INSERT_LINHA, (pid, "Operacional", "manual", 1, 20800, 20800, 0, 4))
    c.rollback()

    dbmod.init_db(c)

    # Linha pré-existente preservada, com override e quantidade intactos
    linha = c.execute("SELECT * FROM linhas_custo WHERE descricao = 'Porteiro diurno'").fetchone()
    assert (linha["proposta_id"], linha["quantidade"], linha["valor_final_centavos"],
            linha["sobrescrito"]) == (pid, 2, 155000, 1)
    # Nova categoria passa a ser aceita
    c.execute(_INSERT_LINHA, (pid, "Operacional", "manual", 1, 20800, 20800, 0, 4))
    c.commit()
    c.close()
