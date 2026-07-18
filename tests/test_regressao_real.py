"""Regressão com os números de dois documentos de referência (uma proposta de
serviço contínuo e um orçamento de evento único), montados via motor real
(inserir_linha, sincronizar_acessorios, recalcular_derivadas) + overrides — não
por cálculo solto — para exercitar a máquina de derivadas/overrides de ponta a
ponta."""
from app import repo_catalogo as rcat
from app import repo_clientes as rc
from app import repo_propostas as rp


def test_regressao_continuo(conn):
    rcat.seed_inicial(conn)
    cid = rc.criar_cliente(conn, "Cliente Exemplo Ltda", "11.222.333/0001-81",
                           "Av. Exemplo, 1000")
    pid = rp.criar_proposta(conn, "continuo")
    rp.definir_cliente(conn, pid, cid)

    # Portaria noturna (12x36): 1.853,00/mês x 2 | Portaria diurna (12x36): 1.600,00/mês x 1
    rp.inserir_linha(conn, pid, "Portaria noturna (12x36)", "mao_de_obra", 2, 185300)
    rp.inserir_linha(conn, pid, "Portaria diurna (12x36)", "mao_de_obra", 1, 160000)

    # Alimentação 580,00 e Transporte 180,00 por profissional (3 profissionais)
    rp.sincronizar_acessorios(conn, pid, valor_alimentacao=58000, valor_transporte=18000)
    rp.recalcular_derivadas(conn, pid, rcat.params_vigentes(conn))

    linhas = {l["descricao"]: l for l in rp.linhas_da_proposta(conn, pid)}
    assert linhas["Alimentação"]["quantidade"] == 3
    assert linhas["Transporte"]["quantidade"] == 3

    # Encargos Sociais e Margem administrativa do documento real (valores fechados,
    # não os percentuais padrão do catálogo) — sobrescrevem o sugerido calculado
    rp.sobrescrever_linha(conn, linhas["Encargos sociais"]["id"], 306600)
    rp.sobrescrever_linha(conn, linhas["Margem administrativa"]["id"], 114000)

    # O documento real também tinha uma linha "Operacional" (R$ 208,00), somada
    # por fora das derivadas percentuais — exatamente o caso da categoria manual.
    rp.inserir_linha(conn, pid, "Operacional", "manual", 1, 20800)

    assert rp.total_proposta(conn, pid) == 1200000  # R$ 12.000,00, igual ao documento de referência


def test_regressao_orcamento_evento(conn):
    rcat.seed_inicial(conn)
    cid = rc.criar_cliente(conn, "Empresa XYZ", "11.222.333/0001-81",
                           "Avenida Nome Sobrenome, 000")
    pid = rp.criar_proposta(conn, "evento")
    rp.definir_cliente(conn, pid, cid)

    # Segurança de evento (12h): 220,00 x 6 | Serviços gerais de evento (12h): 220,00 x 2
    rp.inserir_linha(conn, pid, "Segurança de evento (12h)", "mao_de_obra", 6, 22000)
    rp.inserir_linha(conn, pid, "Serviços gerais de evento (12h)", "mao_de_obra", 2, 22000)

    # Alimentação 20,00 e Transporte 40,00 por profissional (8 profissionais)
    rp.sincronizar_acessorios(conn, pid, valor_alimentacao=2000, valor_transporte=4000)
    rp.recalcular_derivadas(conn, pid, rcat.params_vigentes(conn))

    linhas = {l["descricao"]: l for l in rp.linhas_da_proposta(conn, pid)}
    assert linhas["Alimentação"]["quantidade"] == 8
    assert linhas["Transporte"]["quantidade"] == 8

    # O documento real de evento não usa encargos sociais/margem percentuais —
    # zeramos ambos (valida override para 0) e o custo de EPIs/trajes/material
    # de limpeza (R$ 160,00 no total) entra como linha manual, como no documento.
    rp.sobrescrever_linha(conn, linhas["Encargos sociais"]["id"], 0)
    rp.sobrescrever_linha(conn, linhas["Margem administrativa"]["id"], 0)
    rp.inserir_linha(conn, pid, "EPIs, trajes e material de limpeza", "manual", 1, 16000)

    encargos = [l for l in rp.linhas_da_proposta(conn, pid) if l["descricao"] == "Encargos sociais"][0]
    assert encargos["valor_final_centavos"] == 0 and encargos["sobrescrito"] == 1

    assert rp.total_proposta(conn, pid) == 240000  # R$ 2.400,00, igual ao modelo real
