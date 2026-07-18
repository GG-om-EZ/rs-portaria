"""Cadastro de clientes. CNPJ armazenado com máscara padrão XX.XXX.XXX/XXXX-XX."""
import re
import sqlite3


def _somente_digitos(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


def _dv(digitos: str, pesos: list[int]) -> int:
    soma = sum(int(d) * p for d, p in zip(digitos, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def validar_cnpj(cnpj: str) -> bool:
    d = _somente_digitos(cnpj)
    if len(d) != 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    return int(d[12]) == _dv(d[:12], pesos1) and int(d[13]) == _dv(d[:13], pesos2)


def formatar_cnpj(cnpj: str) -> str:
    d = _somente_digitos(cnpj)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def criar_cliente(
    conn: sqlite3.Connection,
    razao_social: str,
    cnpj: str,
    endereco: str,
    email: str = "",
    telefone: str = "",
) -> int:
    if not validar_cnpj(cnpj):
        raise ValueError("CNPJ inválido")
    try:
        cur = conn.execute(
            "INSERT INTO clientes (razao_social, cnpj, endereco, email, telefone)"
            " VALUES (?, ?, ?, ?, ?)",
            (razao_social.strip(), formatar_cnpj(cnpj), endereco.strip(), email.strip(), telefone.strip()),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError("Já existe cliente com esse CNPJ") from exc
    conn.commit()
    return cur.lastrowid


def buscar_clientes(conn: sqlite3.Connection, termo: str = "") -> list[sqlite3.Row]:
    like = f"%{termo.strip()}%"
    return conn.execute(
        "SELECT * FROM clientes WHERE razao_social LIKE ? COLLATE NOCASE OR cnpj LIKE ?"
        " ORDER BY razao_social",
        (like, like),
    ).fetchall()


def obter_cliente(conn: sqlite3.Connection, cliente_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,)).fetchone()


def atualizar_cliente(conn: sqlite3.Connection, cliente_id: int, **campos) -> None:
    permitidos = {"razao_social", "endereco", "email", "telefone"}
    invalidos = set(campos) - permitidos
    if invalidos:
        raise ValueError(f"Campos não editáveis: {invalidos}")
    if not campos:
        return  # sem campos: no-op (evita SQL inválido)
    valores = [v.strip() if isinstance(v, str) else v for v in campos.values()]
    sets = ", ".join(f"{c} = ?" for c in campos)
    conn.execute(
        f"UPDATE clientes SET {sets} WHERE id = ?", (*valores, cliente_id)
    )
    conn.commit()
