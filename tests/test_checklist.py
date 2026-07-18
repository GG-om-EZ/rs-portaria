import pytest

from app import checklist, repo_clientes as rc, repo_propostas as rp


def _completa_continuo(conn):
    cid = rc.criar_cliente(conn, "Cliente Exemplo", "11.222.333/0001-81", "Av. Exemplo, 1000")
    pid = rp.criar_proposta(conn, "continuo")
    rp.definir_cliente(conn, pid, cid)
    rp.atualizar_dados(conn, pid, {
        "endereco_servico": "Av. Exemplo, 1000",
        "duracao_meses": "12",
        "data_inicio": "2026-08-01",
        "hora_inicio_turno": "18:00",
        "hora_fim_turno": "06:00",
        "formas_pagamento": "PIX",
        "vencimento": "todo dia 05",
    })
    rp.inserir_linha(conn, pid, "Portaria noturna", "mao_de_obra", 2, 100000)
    return pid


def test_proposta_completa_pode_emitir(conn):
    pid = _completa_continuo(conn)
    itens = checklist.avaliar(conn, pid)
    assert checklist.pode_emitir(itens) is True
    assert all(i.ok for i in itens if i.critico)


def test_sem_cliente_bloqueia(conn):
    pid = rp.criar_proposta(conn, "continuo")
    itens = checklist.avaliar(conn, pid)
    assert checklist.pode_emitir(itens) is False


def test_sem_linha_de_mao_de_obra_bloqueia(conn):
    pid = _completa_continuo(conn)
    for linha in rp.linhas_da_proposta(conn, pid):
        rp.remover_linha(conn, linha["id"])
    assert checklist.pode_emitir(checklist.avaliar(conn, pid)) is False


def test_evento_exige_data_limite(conn):
    cid = rc.criar_cliente(conn, "XYZ", "11.444.777/0001-61", "End.")
    pid = rp.criar_proposta(conn, "evento")
    rp.definir_cliente(conn, pid, cid)
    rp.atualizar_dados(conn, pid, {
        "endereco_servico": "Local do evento",
        "data_evento": "2026-09-10",
        "hora_inicio": "18:00",
        "hora_fim": "02:00",
        "formas_pagamento": "PIX",
    })
    rp.inserir_linha(conn, pid, "Segurança", "mao_de_obra", 6, 22000)
    assert checklist.pode_emitir(checklist.avaliar(conn, pid)) is False  # falta data_limite_pagamento

    rp.atualizar_dados(conn, pid, {"data_limite_pagamento": "2026-09-09"})
    assert checklist.pode_emitir(checklist.avaliar(conn, pid)) is True


def test_observacoes_nao_critico(conn):
    pid = _completa_continuo(conn)
    itens = {i.rotulo: i for i in checklist.avaliar(conn, pid)}
    obs = itens["Observações preenchidas"]
    assert obs.ok is False and obs.critico is False


def test_campo_none_conta_como_vazio(conn):
    # Campo explicitamente limpo (None no dados_json) não pode passar no checklist
    pid = _completa_continuo(conn)
    rp.atualizar_dados(conn, pid, {"endereco_servico": None})
    itens = {i.rotulo: i for i in checklist.avaliar(conn, pid)}
    assert itens["Endereço do serviço informado"].ok is False
    assert checklist.pode_emitir(list(itens.values())) is False


def test_avaliar_proposta_inexistente(conn):
    with pytest.raises(ValueError):
        checklist.avaliar(conn, 99999)
