from decimal import Decimal

from app import repo_catalogo as rcat


def test_parametro_vigente_respeita_vigencia(conn):
    rcat.definir_parametro(conn, "pct_noturno", "0.20", "2025-01-01")
    rcat.definir_parametro(conn, "pct_noturno", "0.25", "2026-01-01")
    rcat.definir_parametro(conn, "pct_noturno", "0.30", "2099-01-01")  # futura

    assert rcat.parametro_vigente(conn, "pct_noturno", em="2025-06-01") == "0.20"
    assert rcat.parametro_vigente(conn, "pct_noturno", em="2026-07-15") == "0.25"
    assert rcat.parametro_vigente(conn, "inexistente") is None
    assert len(rcat.historico_parametro(conn, "pct_noturno")) == 3


def test_params_vigentes_monta_dataclass(conn):
    rcat.seed_inicial(conn)
    p = rcat.params_vigentes(conn)
    assert p.pct_noturno == Decimal("0.20")
    assert p.divisor_horas == 220
    assert rcat.param_int(conn, "valor_alimentacao_continuo") == 58000


def test_funcoes_crud(conn):
    fid = rcat.criar_funcao(conn, "Portaria noturna (12x36)", "continuo", 160000, aplica_noturno=True)
    f = rcat.obter_funcao(conn, fid)
    assert f["aplica_noturno"] == 1
    assert [r["id"] for r in rcat.listar_funcoes(conn, tipo="continuo")] == [fid]

    rcat.atualizar_funcao(conn, fid, valor_base_centavos=170000, ativa=0)
    assert rcat.listar_funcoes(conn, tipo="continuo") == []
    assert rcat.obter_funcao(conn, fid)["valor_base_centavos"] == 170000


def test_seed_idempotente(conn):
    rcat.seed_inicial(conn)
    rcat.seed_inicial(conn)
    assert rcat.parametro_vigente(conn, "empresa_nome") == "RS PORTARIA E SERVICOS"
    assert len(rcat.listar_funcoes(conn)) == 5
    assert len(rcat.historico_parametro(conn, "empresa_nome")) == 1
