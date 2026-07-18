import json

from app import db as dbmod


def _conn(tmp_path):
    return dbmod.get_conn(tmp_path / "app.db")


def _fluxo_ate_custos(client, tmp_path):
    r = client.post("/propostas/nova", data={"tipo": "continuo"}, follow_redirects=False)
    pid = int(r.headers["location"].split("/")[2])
    client.post(f"/propostas/{pid}/cliente/novo", data={
        "razao_social": "Cliente Exemplo Ltda", "cnpj": "11.222.333/0001-81",
        "endereco": "Av. Exemplo, 1000", "email": "", "telefone": "",
    })
    client.post(f"/propostas/{pid}/local", data={
        "descricao_local": "Empresa", "endereco_servico": "Av. Exemplo, 1000",
        "duracao_meses": "12", "data_inicio": "2026-08-01",
    })
    conn = _conn(tmp_path)
    noturna = conn.execute(
        "SELECT id FROM funcoes WHERE nome LIKE 'Portaria noturna%'").fetchone()["id"]
    client.post(f"/propostas/{pid}/servicos", data={
        "hora_inicio_turno": "18:00", "hora_fim_turno": "06:00", "plantoes_mes": "15",
        "trajes": "Fardamento padrão da empresa prestadora", "observacoes": "",
        f"qtd_{noturna}": "2",
    })
    return pid, conn


def test_custos_override_e_restauracao(client, tmp_path):
    pid, conn = _fluxo_ate_custos(client, tmp_path)
    r = client.get(f"/propostas/{pid}/custos")
    assert r.status_code == 200 and "Portaria noturna" in r.text

    linha = conn.execute(
        "SELECT id FROM linhas_custo WHERE proposta_id=? AND categoria='mao_de_obra'",
        (pid,)).fetchone()["id"]
    r = client.post(f"/propostas/{pid}/linhas/{linha}/valor",
                    data={"valor": "1.853,00"}, headers={"HX-Request": "true"})
    assert r.status_code == 200 and "sobrescrita" in r.text  # linha destacada
    row = conn.execute("SELECT * FROM linhas_custo WHERE id=?", (linha,)).fetchone()
    assert row["valor_final_centavos"] == 185300 and row["sobrescrito"] == 1

    client.post(f"/propostas/{pid}/linhas/{linha}/restaurar", headers={"HX-Request": "true"})
    row = conn.execute("SELECT * FROM linhas_custo WHERE id=?", (linha,)).fetchone()
    assert row["sobrescrito"] == 0


def test_emissao_bloqueada_sem_pagamento(client, tmp_path):
    pid, _ = _fluxo_ate_custos(client, tmp_path)
    r = client.get(f"/propostas/{pid}/revisao")
    assert "check-falha" in r.text
    r = client.post(f"/propostas/{pid}/emitir", follow_redirects=False)
    assert r.status_code == 200 and "pendências" in r.text.lower()


def test_fluxo_completo_ate_pdf(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.pdf.gerar_pdf", lambda s: b"%PDF-fake")
    pid, conn = _fluxo_ate_custos(client, tmp_path)
    client.post(f"/propostas/{pid}/pagamento", data={
        "formas_pagamento": ["PIX", "Transferência bancária"],
        "vencimento": "todo dia 05", "parcela_ingresso": "on",
    })
    r = client.get(f"/propostas/{pid}/revisao")
    assert "Emitir PDF" in r.text  # críticos todos ok -> botão liberado

    r = client.post(f"/propostas/{pid}/emitir", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/emitida")

    row = conn.execute("SELECT * FROM propostas WHERE id=?", (pid,)).fetchone()
    assert row["status"] == "emitida" and row["numero"].startswith("RS-")
    assert row["pdf_arquivado"] == 1
    snap = json.loads(row["snapshot_json"])
    assert snap["dados"]["parcela_ingresso"] == "sim"

    r = client.get(f"/propostas/{pid}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content == b"%PDF-fake"

    import pathlib, os
    arquivos = list(pathlib.Path(os.environ["RSP_ARQUIVO_DIR"]).glob("*.pdf"))
    assert len(arquivos) == 1 and arquivos[0].name.startswith(row["numero"])


def test_preview_rascunho(client, tmp_path):
    pid, _ = _fluxo_ate_custos(client, tmp_path)
    r = client.get(f"/propostas/{pid}/preview")
    assert r.status_code == 200 and "RASCUNHO" in r.text


def test_valor_com_linha_de_outra_proposta_da_404(client, tmp_path):
    pid_a, conn = _fluxo_ate_custos(client, tmp_path)
    pid_b, _ = _fluxo_ate_custos(client, tmp_path)
    linha_b = conn.execute(
        "SELECT id FROM linhas_custo WHERE proposta_id=? AND categoria='mao_de_obra'",
        (pid_b,)).fetchone()["id"]
    antes = conn.execute(
        "SELECT valor_final_centavos, sobrescrito FROM linhas_custo WHERE id=?",
        (linha_b,)).fetchone()

    # tenta mutar a linha da proposta B através da proposta A
    r = client.post(f"/propostas/{pid_a}/linhas/{linha_b}/valor",
                    data={"valor": "9.999,00"}, headers={"HX-Request": "true"})
    assert r.status_code == 404

    depois = conn.execute(
        "SELECT valor_final_centavos, sobrescrito FROM linhas_custo WHERE id=?",
        (linha_b,)).fetchone()
    assert depois["valor_final_centavos"] == antes["valor_final_centavos"]
    assert depois["sobrescrito"] == antes["sobrescrito"]

    r = client.post(f"/propostas/{pid_a}/linhas/{linha_b}/restaurar",
                    headers={"HX-Request": "true"})
    assert r.status_code == 404


def _emitir_proposta(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.pdf.gerar_pdf", lambda s: b"%PDF-fake")
    pid, conn = _fluxo_ate_custos(client, tmp_path)
    client.post(f"/propostas/{pid}/pagamento", data={
        "formas_pagamento": ["PIX"], "vencimento": "todo dia 05",
    })
    client.post(f"/propostas/{pid}/emitir", follow_redirects=False)
    return pid, conn


def test_mutacao_de_linha_em_proposta_emitida_redireciona(client, tmp_path, monkeypatch):
    pid, conn = _emitir_proposta(client, tmp_path, monkeypatch)
    linha = conn.execute(
        "SELECT id FROM linhas_custo WHERE proposta_id=? AND categoria='mao_de_obra'",
        (pid,)).fetchone()["id"]
    antes = conn.execute(
        "SELECT valor_final_centavos, sobrescrito FROM linhas_custo WHERE id=?",
        (linha,)).fetchone()

    r = client.post(f"/propostas/{pid}/linhas/{linha}/valor",
                    data={"valor": "9.999,00"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/emitida")

    r = client.post(f"/propostas/{pid}/linhas/{linha}/restaurar", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/emitida")

    depois = conn.execute(
        "SELECT valor_final_centavos, sobrescrito FROM linhas_custo WHERE id=?",
        (linha,)).fetchone()
    assert depois["valor_final_centavos"] == antes["valor_final_centavos"]
    assert depois["sobrescrito"] == antes["sobrescrito"]
