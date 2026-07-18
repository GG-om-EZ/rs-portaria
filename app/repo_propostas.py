"""Propostas, linhas de custo (com override destacável) e duplicação."""
import json
import sqlite3

from app.calc import Params, encargos_centavos, margem_centavos

_ORDEM = {"mao_de_obra": 1, "acessorio": 2, "derivada": 3, "manual": 4}


def criar_proposta(conn: sqlite3.Connection, tipo: str) -> int:
    cur = conn.execute("INSERT INTO propostas (tipo) VALUES (?)", (tipo,))
    conn.commit()
    return cur.lastrowid


def obter_proposta(conn: sqlite3.Connection, pid: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM propostas WHERE id = ?", (pid,)).fetchone()


def dados_de(row: sqlite3.Row) -> dict:
    return json.loads(row["dados_json"])


def _exigir_rascunho(conn: sqlite3.Connection, pid: int) -> sqlite3.Row:
    row = obter_proposta(conn, pid)
    if row is None:
        raise ValueError(f"Proposta {pid} não existe")
    if row["status"] != "rascunho":
        raise RuntimeError("Proposta emitida é imutável — duplique para alterar")
    return row


def atualizar_dados(conn: sqlite3.Connection, pid: int, novos: dict) -> None:
    row = _exigir_rascunho(conn, pid)
    dados = dados_de(row)
    dados.update(novos)
    conn.execute(
        "UPDATE propostas SET dados_json = ? WHERE id = ?",
        (json.dumps(dados, ensure_ascii=False), pid),
    )
    conn.commit()


def definir_cliente(conn: sqlite3.Connection, pid: int, cliente_id: int) -> None:
    _exigir_rascunho(conn, pid)
    conn.execute("UPDATE propostas SET cliente_id = ? WHERE id = ?", (cliente_id, pid))
    conn.commit()


def listar_propostas(conn: sqlite3.Connection, termo: str = "") -> list[sqlite3.Row]:
    like = f"%{termo.strip()}%"
    return conn.execute(
        "SELECT p.*, c.razao_social FROM propostas p"
        " LEFT JOIN clientes c ON c.id = p.cliente_id"
        " WHERE c.razao_social LIKE ? COLLATE NOCASE OR IFNULL(p.numero, '') LIKE ?"
        "    OR ? = '%%'"
        " ORDER BY p.id DESC",
        (like, like, like),
    ).fetchall()


def inserir_linha(
    conn: sqlite3.Connection,
    pid: int,
    descricao: str,
    categoria: str,
    quantidade: int,
    valor_sugerido_centavos: int,
    funcao_id: int | None = None,
) -> int:
    _exigir_rascunho(conn, pid)
    cur = conn.execute(
        "INSERT INTO linhas_custo (proposta_id, funcao_id, descricao, categoria, quantidade,"
        " valor_sugerido_centavos, valor_final_centavos, ordem) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (pid, funcao_id, descricao, categoria, quantidade,
         valor_sugerido_centavos, valor_sugerido_centavos, _ORDEM[categoria]),
    )
    conn.commit()
    return cur.lastrowid


def _exigir_linha_editavel(conn: sqlite3.Connection, linha_id: int) -> None:
    """Garante que a linha existe e pertence a uma proposta em rascunho."""
    row = conn.execute(
        "SELECT proposta_id FROM linhas_custo WHERE id = ?", (linha_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Linha {linha_id} não existe")
    _exigir_rascunho(conn, row["proposta_id"])


def remover_linha(conn: sqlite3.Connection, linha_id: int) -> None:
    _exigir_linha_editavel(conn, linha_id)
    conn.execute("DELETE FROM linhas_custo WHERE id = ?", (linha_id,))
    conn.commit()


def sobrescrever_linha(conn: sqlite3.Connection, linha_id: int, valor_final_centavos: int) -> None:
    _exigir_linha_editavel(conn, linha_id)
    conn.execute(
        "UPDATE linhas_custo SET valor_final_centavos = ?, sobrescrito = 1 WHERE id = ?",
        (valor_final_centavos, linha_id),
    )
    conn.commit()


def restaurar_linha(conn: sqlite3.Connection, linha_id: int) -> None:
    _exigir_linha_editavel(conn, linha_id)
    conn.execute(
        "UPDATE linhas_custo SET valor_final_centavos = valor_sugerido_centavos,"
        " sobrescrito = 0 WHERE id = ?",
        (linha_id,),
    )
    conn.commit()


def atualizar_linha_mao_de_obra(
    conn: sqlite3.Connection, linha_id: int, quantidade: int, valor_sugerido_centavos: int
) -> None:
    """Atualiza quantidade/sugerido de uma linha de mão de obra existente ao
    re-submeter a etapa Serviços, preservando o valor final quando sobrescrito."""
    _exigir_linha_editavel(conn, linha_id)
    row = conn.execute(
        "SELECT sobrescrito, valor_final_centavos FROM linhas_custo WHERE id = ?",
        (linha_id,),
    ).fetchone()
    final = row["valor_final_centavos"] if row["sobrescrito"] else valor_sugerido_centavos
    conn.execute(
        "UPDATE linhas_custo SET quantidade = ?, valor_sugerido_centavos = ?,"
        " valor_final_centavos = ? WHERE id = ?",
        (quantidade, valor_sugerido_centavos, final, linha_id),
    )
    conn.commit()


def linhas_da_proposta(conn: sqlite3.Connection, pid: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM linhas_custo WHERE proposta_id = ? ORDER BY ordem, id", (pid,)
    ).fetchall()


def total_proposta(conn: sqlite3.Connection, pid: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(valor_final_centavos * quantidade), 0) AS t"
        " FROM linhas_custo WHERE proposta_id = ?",
        (pid,),
    ).fetchone()
    return row["t"]


def _soma_categoria(conn, pid: int, categoria: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(valor_final_centavos * quantidade), 0) AS t"
        " FROM linhas_custo WHERE proposta_id = ? AND categoria = ?",
        (pid, categoria),
    ).fetchone()
    return row["t"]


def _upsert_linha_fixa(conn, pid: int, descricao: str, categoria: str,
                       quantidade: int, sugerido: int) -> None:
    """Cria/atualiza linha automática preservando override do valor."""
    row = conn.execute(
        "SELECT * FROM linhas_custo WHERE proposta_id = ? AND descricao = ? AND categoria = ?",
        (pid, descricao, categoria),
    ).fetchone()
    if row is None:
        inserir_linha(conn, pid, descricao, categoria, quantidade, sugerido)
        return
    final = row["valor_final_centavos"] if row["sobrescrito"] else sugerido
    conn.execute(
        "UPDATE linhas_custo SET quantidade = ?, valor_sugerido_centavos = ?,"
        " valor_final_centavos = ? WHERE id = ?",
        (quantidade, sugerido, final, row["id"]),
    )
    conn.commit()


def sincronizar_acessorios(conn: sqlite3.Connection, pid: int,
                           valor_alimentacao: int, valor_transporte: int) -> None:
    """Alimentação/Transporte com quantidade = total de profissionais de mão de obra."""
    _exigir_rascunho(conn, pid)
    profs = conn.execute(
        "SELECT COALESCE(SUM(quantidade), 0) AS n FROM linhas_custo"
        " WHERE proposta_id = ? AND categoria = 'mao_de_obra'",
        (pid,),
    ).fetchone()["n"]
    if profs == 0:
        # Sem mão de obra não há acessórios: remove linhas obsoletas
        conn.execute(
            "DELETE FROM linhas_custo WHERE proposta_id = ? AND categoria = 'acessorio'",
            (pid,),
        )
        conn.commit()
        return
    _upsert_linha_fixa(conn, pid, "Alimentação", "acessorio", profs, valor_alimentacao)
    _upsert_linha_fixa(conn, pid, "Transporte", "acessorio", profs, valor_transporte)


def recalcular_derivadas(conn: sqlite3.Connection, pid: int, params: Params) -> None:
    """Encargos sobre mão de obra; margem sobre mão de obra + acessórios + encargos."""
    _exigir_rascunho(conn, pid)
    base_mo = _soma_categoria(conn, pid, "mao_de_obra")
    if base_mo == 0:
        # Sem mão de obra não há derivadas: remove linhas obsoletas
        conn.execute(
            "DELETE FROM linhas_custo WHERE proposta_id = ? AND categoria = 'derivada'",
            (pid,),
        )
        conn.commit()
        return
    _upsert_linha_fixa(conn, pid, "Encargos sociais", "derivada", 1,
                       encargos_centavos(base_mo, params))
    enc_final = conn.execute(
        "SELECT valor_final_centavos FROM linhas_custo"
        " WHERE proposta_id = ? AND descricao = 'Encargos sociais'",
        (pid,),
    ).fetchone()["valor_final_centavos"]
    base_margem = base_mo + _soma_categoria(conn, pid, "acessorio") + enc_final
    _upsert_linha_fixa(conn, pid, "Margem administrativa", "derivada", 1,
                       margem_centavos(base_margem, params))


def duplicar_proposta(conn: sqlite3.Connection, pid: int) -> int:
    orig = obter_proposta(conn, pid)
    if orig is None:
        raise ValueError(f"Proposta {pid} não existe")
    cur = conn.execute(
        "INSERT INTO propostas (tipo, cliente_id, dados_json) VALUES (?, ?, ?)",
        (orig["tipo"], orig["cliente_id"], orig["dados_json"]),
    )
    novo = cur.lastrowid
    conn.execute(
        "INSERT INTO linhas_custo (proposta_id, funcao_id, descricao, categoria, quantidade,"
        " valor_sugerido_centavos, valor_final_centavos, sobrescrito, ordem)"
        " SELECT ?, funcao_id, descricao, categoria, quantidade,"
        " valor_sugerido_centavos, valor_final_centavos, sobrescrito, ordem"
        " FROM linhas_custo WHERE proposta_id = ?",
        (novo, pid),
    )
    conn.commit()
    return novo
