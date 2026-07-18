from decimal import Decimal

import pytest

from app import repo_propostas as rp
from app.calc import Params

PARAMS = Params(Decimal("0.50"), Decimal("0.20"), Decimal("0.10"))


def _proposta_com_linhas(conn):
    pid = rp.criar_proposta(conn, "continuo")
    rp.inserir_linha(conn, pid, "Portaria noturna (12x36)", "mao_de_obra", 2, 100000)
    rp.inserir_linha(conn, pid, "Portaria diurna (12x36)", "mao_de_obra", 1, 80000)
    return pid


def test_criar_e_atualizar_dados(conn):
    pid = rp.criar_proposta(conn, "continuo")
    rp.atualizar_dados(conn, pid, {"endereco_servico": "Av. X, 100"})
    rp.atualizar_dados(conn, pid, {"duracao_meses": "12"})
    dados = rp.dados_de(rp.obter_proposta(conn, pid))
    assert dados == {"endereco_servico": "Av. X, 100", "duracao_meses": "12"}


def test_linhas_override_e_total(conn):
    pid = _proposta_com_linhas(conn)
    linhas = rp.linhas_da_proposta(conn, pid)
    assert rp.total_proposta(conn, pid) == 2 * 100000 + 80000

    alvo = linhas[0]["id"]
    rp.sobrescrever_linha(conn, alvo, 90000)
    linha = [r for r in rp.linhas_da_proposta(conn, pid) if r["id"] == alvo][0]
    assert linha["sobrescrito"] == 1 and linha["valor_final_centavos"] == 90000
    assert linha["valor_sugerido_centavos"] == 100000  # sugerido preservado
    assert rp.total_proposta(conn, pid) == 2 * 90000 + 80000

    rp.restaurar_linha(conn, alvo)
    linha = [r for r in rp.linhas_da_proposta(conn, pid) if r["id"] == alvo][0]
    assert linha["sobrescrito"] == 0 and linha["valor_final_centavos"] == 100000


def test_sincronizar_acessorios(conn):
    pid = _proposta_com_linhas(conn)  # 3 profissionais
    rp.sincronizar_acessorios(conn, pid, valor_alimentacao=58000, valor_transporte=18000)
    acess = {r["descricao"]: r for r in rp.linhas_da_proposta(conn, pid) if r["categoria"] == "acessorio"}
    assert acess["Alimentação"]["quantidade"] == 3
    assert acess["Transporte"]["valor_final_centavos"] == 18000

    # sobrescreve alimentação e adiciona mais um profissional: quantidade muda, valor mantido
    rp.sobrescrever_linha(conn, acess["Alimentação"]["id"], 60000)
    rp.inserir_linha(conn, pid, "Auxiliar", "mao_de_obra", 1, 70000)
    rp.sincronizar_acessorios(conn, pid, valor_alimentacao=58000, valor_transporte=18000)
    acess = {r["descricao"]: r for r in rp.linhas_da_proposta(conn, pid) if r["categoria"] == "acessorio"}
    assert acess["Alimentação"]["quantidade"] == 4
    assert acess["Alimentação"]["valor_final_centavos"] == 60000  # override respeitado


def test_recalcular_derivadas(conn):
    pid = _proposta_com_linhas(conn)  # mão de obra = 280.000
    rp.recalcular_derivadas(conn, pid, PARAMS)
    deriv = {r["descricao"]: r for r in rp.linhas_da_proposta(conn, pid) if r["categoria"] == "derivada"}
    assert deriv["Encargos sociais"]["valor_final_centavos"] == 140000        # 50% de 280.000
    assert deriv["Margem administrativa"]["valor_final_centavos"] == 42000    # 10% de 420.000

    # override na margem sobrevive a novo recálculo; encargos acompanham a base
    rp.sobrescrever_linha(conn, deriv["Margem administrativa"]["id"], 114000)
    rp.inserir_linha(conn, pid, "Extra", "mao_de_obra", 1, 20000)
    rp.recalcular_derivadas(conn, pid, PARAMS)
    deriv = {r["descricao"]: r for r in rp.linhas_da_proposta(conn, pid) if r["categoria"] == "derivada"}
    assert deriv["Encargos sociais"]["valor_final_centavos"] == 150000        # 50% de 300.000
    assert deriv["Margem administrativa"]["valor_final_centavos"] == 114000
    assert deriv["Margem administrativa"]["sobrescrito"] == 1


def test_duplicar_proposta(conn):
    pid = _proposta_com_linhas(conn)
    rp.atualizar_dados(conn, pid, {"endereco_servico": "Av. X"})
    novo = rp.duplicar_proposta(conn, pid)
    assert novo != pid
    nova_row = rp.obter_proposta(conn, novo)
    assert nova_row["status"] == "rascunho" and nova_row["numero"] is None
    assert rp.dados_de(nova_row)["endereco_servico"] == "Av. X"
    assert len(rp.linhas_da_proposta(conn, novo)) == 2


def test_nao_edita_proposta_emitida(conn):
    pid = rp.criar_proposta(conn, "evento")
    conn.execute("UPDATE propostas SET status = 'emitida' WHERE id = ?", (pid,))
    with pytest.raises(RuntimeError):
        rp.atualizar_dados(conn, pid, {"x": "1"})


def test_nao_muta_linhas_de_proposta_emitida(conn):
    pid = _proposta_com_linhas(conn)
    linha_id = rp.linhas_da_proposta(conn, pid)[0]["id"]
    conn.execute("UPDATE propostas SET status = 'emitida' WHERE id = ?", (pid,))
    with pytest.raises(RuntimeError):
        rp.sobrescrever_linha(conn, linha_id, 90000)
    with pytest.raises(RuntimeError):
        rp.restaurar_linha(conn, linha_id)
    with pytest.raises(RuntimeError):
        rp.remover_linha(conn, linha_id)


def test_linha_inexistente_levanta_valueerror(conn):
    with pytest.raises(ValueError):
        rp.sobrescrever_linha(conn, 9999, 100)
    with pytest.raises(ValueError):
        rp.restaurar_linha(conn, 9999)
    with pytest.raises(ValueError):
        rp.remover_linha(conn, 9999)


def test_atualizar_linha_mao_de_obra_preserva_override(conn):
    pid = _proposta_com_linhas(conn)
    linha_id = rp.linhas_da_proposta(conn, pid)[0]["id"]  # noturna, qtd 2, 100000

    rp.sobrescrever_linha(conn, linha_id, 90000)
    rp.atualizar_linha_mao_de_obra(conn, linha_id, 3, 105000)
    linha = [r for r in rp.linhas_da_proposta(conn, pid) if r["id"] == linha_id][0]
    assert linha["quantidade"] == 3
    assert linha["valor_sugerido_centavos"] == 105000  # sugerido sempre atualiza
    assert linha["valor_final_centavos"] == 90000       # override preservado
    assert linha["sobrescrito"] == 1

    rp.restaurar_linha(conn, linha_id)
    rp.atualizar_linha_mao_de_obra(conn, linha_id, 4, 110000)
    linha = [r for r in rp.linhas_da_proposta(conn, pid) if r["id"] == linha_id][0]
    assert linha["valor_final_centavos"] == 110000  # sem override, final acompanha sugerido


def test_linha_manual_fica_fora_das_bases_e_entra_no_total(conn):
    pid = _proposta_com_linhas(conn)  # mão de obra = 280.000
    rp.recalcular_derivadas(conn, pid, PARAMS)
    rp.inserir_linha(conn, pid, "Operacional", "manual", 1, 20800)
    rp.recalcular_derivadas(conn, pid, PARAMS)

    deriv = {r["descricao"]: r for r in rp.linhas_da_proposta(conn, pid) if r["categoria"] == "derivada"}
    assert deriv["Encargos sociais"]["valor_final_centavos"] == 140000     # base só mão de obra
    assert deriv["Margem administrativa"]["valor_final_centavos"] == 42000  # manual fora da base
    assert rp.total_proposta(conn, pid) == 280000 + 140000 + 42000 + 20800
    assert rp.linhas_da_proposta(conn, pid)[-1]["descricao"] == "Operacional"  # após derivadas


def test_linha_manual_sobrevive_a_sincronizacoes_sem_mao_de_obra(conn):
    pid = _proposta_com_linhas(conn)
    rp.sincronizar_acessorios(conn, pid, valor_alimentacao=58000, valor_transporte=18000)
    rp.recalcular_derivadas(conn, pid, PARAMS)
    rp.inserir_linha(conn, pid, "EPIs, trajes e material", "manual", 1, 16000)

    for r in rp.linhas_da_proposta(conn, pid):
        if r["categoria"] == "mao_de_obra":
            rp.remover_linha(conn, r["id"])
    rp.sincronizar_acessorios(conn, pid, valor_alimentacao=58000, valor_transporte=18000)
    rp.recalcular_derivadas(conn, pid, PARAMS)

    restantes = rp.linhas_da_proposta(conn, pid)
    assert [r["categoria"] for r in restantes] == ["manual"]
    assert rp.total_proposta(conn, pid) == 16000


def test_linha_manual_copiada_na_duplicacao(conn):
    pid = _proposta_com_linhas(conn)
    rp.inserir_linha(conn, pid, "Operacional", "manual", 1, 20800)
    novo = rp.duplicar_proposta(conn, pid)
    copiada = [r for r in rp.linhas_da_proposta(conn, novo) if r["categoria"] == "manual"]
    assert len(copiada) == 1
    assert copiada[0]["descricao"] == "Operacional"
    assert copiada[0]["valor_final_centavos"] == 20800


def test_derivadas_e_acessorios_somem_sem_mao_de_obra(conn):
    pid = _proposta_com_linhas(conn)
    rp.sincronizar_acessorios(conn, pid, valor_alimentacao=58000, valor_transporte=18000)
    rp.recalcular_derivadas(conn, pid, PARAMS)
    assert any(r["categoria"] == "acessorio" for r in rp.linhas_da_proposta(conn, pid))
    assert any(r["categoria"] == "derivada" for r in rp.linhas_da_proposta(conn, pid))

    for r in rp.linhas_da_proposta(conn, pid):
        if r["categoria"] == "mao_de_obra":
            rp.remover_linha(conn, r["id"])
    rp.sincronizar_acessorios(conn, pid, valor_alimentacao=58000, valor_transporte=18000)
    rp.recalcular_derivadas(conn, pid, PARAMS)
    assert rp.linhas_da_proposta(conn, pid) == []
    assert rp.total_proposta(conn, pid) == 0
