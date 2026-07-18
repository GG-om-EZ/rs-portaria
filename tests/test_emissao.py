import json
from pathlib import Path

import pytest

from app import emissao, repo_catalogo as rcat, repo_clientes as rc, repo_propostas as rp


@pytest.fixture
def proposta_pronta(conn):
    rcat.seed_inicial(conn)
    cid = rc.criar_cliente(conn, "Cliente Exemplo Ltda", "11.222.333/0001-81", "Av. Exemplo, 1000")
    pid = rp.criar_proposta(conn, "continuo")
    rp.definir_cliente(conn, pid, cid)
    rp.atualizar_dados(conn, pid, {
        "endereco_servico": "Av. Exemplo, 1000", "duracao_meses": "12",
        "data_inicio": "2026-08-01", "hora_inicio_turno": "18:00",
        "hora_fim_turno": "06:00", "formas_pagamento": "PIX", "vencimento": "dia 05",
    })
    rp.inserir_linha(conn, pid, "Portaria noturna (12x36)", "mao_de_obra", 2, 185300)
    return pid


def test_proximo_numero_sequencial_por_ano(conn):
    assert emissao.proximo_numero(conn, 2026) == "RS-2026-0001"
    assert emissao.proximo_numero(conn, 2026) == "RS-2026-0002"
    assert emissao.proximo_numero(conn, 2027) == "RS-2027-0001"


def test_montar_snapshot_rascunho(conn, proposta_pronta):
    snap = emissao.montar_snapshot(conn, proposta_pronta)
    assert snap["numero"] == "RASCUNHO"
    assert snap["empresa"]["cnpj"] == "11.444.777/0001-61"
    assert snap["cliente"]["razao_social"] == "Cliente Exemplo Ltda"
    assert snap["total_centavos"] == 2 * 185300
    assert snap["total_fmt"] == "3.706,00"
    assert "22h" in snap["nota_metodologica"]
    json.dumps(snap)  # precisa ser serializável


def test_emitir_congela_e_arquiva(conn, proposta_pronta, tmp_path):
    arquivo = tmp_path / "enviadas"
    snap = emissao.emitir(conn, proposta_pronta, arquivo,
                          gerador_pdf=lambda s: b"%PDF-fake")
    row = rp.obter_proposta(conn, proposta_pronta)
    assert row["status"] == "emitida"
    assert row["numero"] == "RS-2026-0001" == snap["numero"]
    assert row["pdf_arquivado"] == 1
    assert json.loads(row["snapshot_json"])["total_centavos"] == snap["total_centavos"]
    assert (arquivo / "RS-2026-0001 - Cliente Exemplo Ltda.pdf").read_bytes() == b"%PDF-fake"

    with pytest.raises(RuntimeError):  # emitida é imutável
        rp.atualizar_dados(conn, proposta_pronta, {"x": "1"})


def test_emitir_bloqueia_reemissao(conn, proposta_pronta, tmp_path):
    arquivo = tmp_path / "enviadas"
    snap1 = emissao.emitir(conn, proposta_pronta, arquivo, gerador_pdf=lambda s: b"%PDF-1")

    with pytest.raises(ValueError, match="já emitida"):
        emissao.emitir(conn, proposta_pronta, arquivo, gerador_pdf=lambda s: b"%PDF-2")

    row = rp.obter_proposta(conn, proposta_pronta)
    assert row["numero"] == snap1["numero"]
    assert json.loads(row["snapshot_json"])["total_centavos"] == snap1["total_centavos"]
    assert row["pdf_arquivado"] == 1
    assert (arquivo / f"{snap1['numero']} - Cliente Exemplo Ltda.pdf").read_bytes() == b"%PDF-1"

    # sequência não foi consumida pela tentativa bloqueada: a próxima proposta
    # nova recebe o número seguinte correto, sem "buraco" nem reuso
    cid2 = rc.criar_cliente(conn, "Empresa Gama", "11.444.777/0001-61", "Rua G, 10")
    outra = rp.criar_proposta(conn, "continuo")
    rp.definir_cliente(conn, outra, cid2)
    rp.atualizar_dados(conn, outra, {
        "endereco_servico": "Rua G, 10", "duracao_meses": "6",
        "data_inicio": "2026-09-01", "hora_inicio_turno": "18:00",
        "hora_fim_turno": "06:00", "formas_pagamento": "PIX", "vencimento": "dia 10",
    })
    rp.inserir_linha(conn, outra, "Portaria noturna (12x36)", "mao_de_obra", 1, 185300)
    snap2 = emissao.emitir(conn, outra, arquivo, gerador_pdf=lambda s: b"%PDF-3")
    assert snap2["numero"] == "RS-2026-0002"


def test_emitir_bloqueia_checklist_pendente(conn, tmp_path):
    rcat.seed_inicial(conn)
    pid = rp.criar_proposta(conn, "continuo")
    with pytest.raises(ValueError, match="[Cc]hecklist"):
        emissao.emitir(conn, pid, tmp_path, gerador_pdf=lambda s: b"%PDF")
    assert rp.obter_proposta(conn, pid)["status"] == "rascunho"


def test_falha_de_pdf_preserva_rascunho(conn, proposta_pronta, tmp_path):
    def quebra(_):
        raise RuntimeError("pango explodiu")

    with pytest.raises(RuntimeError):
        emissao.emitir(conn, proposta_pronta, tmp_path, gerador_pdf=quebra)
    row = rp.obter_proposta(conn, proposta_pronta)
    assert row["status"] == "rascunho" and row["numero"] is None
    # sequência não foi consumida
    snap = emissao.emitir(conn, proposta_pronta, tmp_path, gerador_pdf=lambda s: b"%PDF")
    assert snap["numero"] == "RS-2026-0001"


def test_rearquivar_tolera_falha_individual_de_pdf(conn, proposta_pronta, tmp_path):
    # Segunda proposta pronta, de outro cliente
    cid2 = rc.criar_cliente(conn, "Empresa Beta", "11.444.777/0001-61", "Rua B, 99")
    pid2 = rp.criar_proposta(conn, "continuo")
    rp.definir_cliente(conn, pid2, cid2)
    rp.atualizar_dados(conn, pid2, {
        "endereco_servico": "Rua B, 99", "duracao_meses": "6",
        "data_inicio": "2026-09-01", "hora_inicio_turno": "18:00",
        "hora_fim_turno": "06:00", "formas_pagamento": "PIX", "vencimento": "dia 10",
    })
    rp.inserir_linha(conn, pid2, "Portaria noturna (12x36)", "mao_de_obra", 1, 185300)

    # Emite as duas com arquivamento falhando (diretório sob um arquivo)
    trava = tmp_path / "trava"
    trava.write_text("não sou um diretório")
    snap1 = emissao.emitir(conn, proposta_pronta, trava / "sub", gerador_pdf=lambda s: b"%PDF")
    snap2 = emissao.emitir(conn, pid2, trava / "sub", gerador_pdf=lambda s: b"%PDF")
    assert rp.obter_proposta(conn, proposta_pronta)["pdf_arquivado"] == 0
    assert rp.obter_proposta(conn, pid2)["pdf_arquivado"] == 0

    # Gerador falha só na primeira; a segunda deve ser regravada mesmo assim
    def gerador(snapshot):
        if snapshot["numero"] == snap1["numero"]:
            raise RuntimeError("pango explodiu")
        return b"%PDF"

    destino = tmp_path / "ok"
    n = emissao.rearquivar_pendentes(conn, destino, gerador_pdf=gerador)
    assert n == 1
    assert rp.obter_proposta(conn, proposta_pronta)["pdf_arquivado"] == 0
    assert rp.obter_proposta(conn, pid2)["pdf_arquivado"] == 1
    assert (destino / f"{snap2['numero']} - Empresa Beta.pdf").exists()


def test_arquivo_inacessivel_nao_impede_emissao(conn, proposta_pronta, tmp_path):
    trava = tmp_path / "trava"
    trava.write_text("sou um arquivo, não um diretório")
    snap = emissao.emitir(conn, proposta_pronta, trava / "sub",
                          gerador_pdf=lambda s: b"%PDF")
    row = rp.obter_proposta(conn, proposta_pronta)
    assert row["status"] == "emitida" and row["pdf_arquivado"] == 0

    destino = tmp_path / "ok"
    n = emissao.rearquivar_pendentes(conn, destino, gerador_pdf=lambda s: b"%PDF")
    assert n == 1
    assert rp.obter_proposta(conn, proposta_pronta)["pdf_arquivado"] == 1
    assert (destino / f"{snap['numero']} - Cliente Exemplo Ltda.pdf").exists()
