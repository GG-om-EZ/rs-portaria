import pytest

from app import repo_clientes as rc


def test_validar_cnpj():
    assert rc.validar_cnpj("11.444.777/0001-61") is True   # CNPJ de exemplo (válido)
    assert rc.validar_cnpj("11444777000161") is True       # sem máscara
    assert rc.validar_cnpj("11.222.333/0001-81") is True
    assert rc.validar_cnpj("11.444.777/0001-62") is False  # DV errado
    assert rc.validar_cnpj("123") is False
    assert rc.validar_cnpj("") is False


def test_criar_e_buscar_cliente(conn):
    cid = rc.criar_cliente(
        conn,
        razao_social="Cliente Exemplo Ltda",
        cnpj="11.222.333/0001-81",
        endereco="Avenida Exemplo, 1000 – Centro, Cidade – UF",
        email="contato@exemplo.com.br",
    )
    row = rc.obter_cliente(conn, cid)
    assert row["razao_social"] == "Cliente Exemplo Ltda"
    assert [r["id"] for r in rc.buscar_clientes(conn, "exemplo")] == [cid]
    assert [r["id"] for r in rc.buscar_clientes(conn, "11.222")] == [cid]
    assert rc.buscar_clientes(conn, "inexistente") == []


def test_cnpj_invalido_rejeitado(conn):
    with pytest.raises(ValueError):
        rc.criar_cliente(conn, "X", "11.111.111/0001-00", "End.")


def test_cnpj_duplicado_rejeitado(conn):
    rc.criar_cliente(conn, "A", "11.444.777/0001-61", "End.")
    with pytest.raises(ValueError):
        rc.criar_cliente(conn, "B", "11444777000161", "End.")


def test_atualizar_cliente(conn):
    cid = rc.criar_cliente(conn, "A", "11.444.777/0001-61", "End.")
    rc.atualizar_cliente(conn, cid, telefone="(83) 99999-0000")
    assert rc.obter_cliente(conn, cid)["telefone"] == "(83) 99999-0000"


def test_atualizar_cliente_sem_campos_e_noop(conn):
    cid = rc.criar_cliente(conn, "A", "11.444.777/0001-61", "End.")
    antes = dict(rc.obter_cliente(conn, cid))
    rc.atualizar_cliente(conn, cid)  # sem campos: não deve levantar exceção
    assert dict(rc.obter_cliente(conn, cid)) == antes


def test_atualizar_cliente_aplica_strip(conn):
    cid = rc.criar_cliente(conn, "A", "11.444.777/0001-61", "End.")
    rc.atualizar_cliente(conn, cid, email="  contato@rs.com.br  ")
    assert rc.obter_cliente(conn, cid)["email"] == "contato@rs.com.br"
