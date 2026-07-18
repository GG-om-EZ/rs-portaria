from app import db as dbmod


def _conn(tmp_path):
    return dbmod.get_conn(tmp_path / "app.db")


def _nova(client, tipo="continuo"):
    r = client.post("/propostas/nova", data={"tipo": tipo}, follow_redirects=False)
    return int(r.headers["location"].split("/")[2])


def test_etapa_cliente_criar_e_vincular(client, tmp_path):
    pid = _nova(client)
    r = client.post(f"/propostas/{pid}/cliente/novo", data={
        "razao_social": "Cliente Exemplo Ltda", "cnpj": "11.222.333/0001-81",
        "endereco": "Av. Exemplo, 1000", "email": "x@y.com", "telefone": "",
    }, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/local")
    conn = _conn(tmp_path)
    assert conn.execute("SELECT cliente_id FROM propostas WHERE id=?", (pid,)).fetchone()[0]


def test_etapa_cliente_cnpj_invalido_reexibe_erro(client):
    pid = _nova(client)
    r = client.post(f"/propostas/{pid}/cliente/novo", data={
        "razao_social": "X", "cnpj": "11.111.111/0001-00",
        "endereco": "E", "email": "", "telefone": "",
    })
    assert r.status_code == 200 and "CNPJ inválido" in r.text


def test_etapa_cliente_selecionar_existente(client, tmp_path):
    pid = _nova(client)
    client.post(f"/propostas/{pid}/cliente/novo", data={
        "razao_social": "A", "cnpj": "11.444.777/0001-61",
        "endereco": "E", "email": "", "telefone": "",
    })
    pid2 = _nova(client)
    conn = _conn(tmp_path)
    cid = conn.execute("SELECT id FROM clientes").fetchone()["id"]
    r = client.post(f"/propostas/{pid2}/cliente", data={"cliente_id": cid},
                    follow_redirects=False)
    assert r.status_code == 303


def test_etapa_local_botao_endereco_cliente(client):
    pid = _nova(client)
    client.post(f"/propostas/{pid}/cliente/novo", data={
        "razao_social": "A", "cnpj": "11.444.777/0001-61",
        "endereco": "Av. Exemplo, 1000", "email": "", "telefone": "",
    })
    r = client.get(f"/propostas/{pid}/local")
    # atributo onclick com aspas simples — tojson emite aspas duplas reais,
    # que quebrariam um atributo delimitado por aspas duplas
    assert r.status_code == 200
    assert "onclick='document.getElementById" in r.text


def test_etapa_local_continuo(client, tmp_path):
    pid = _nova(client)
    r = client.post(f"/propostas/{pid}/local", data={
        "descricao_local": "Empresa", "endereco_servico": "Av. Exemplo, 1000",
        "duracao_meses": "12", "data_inicio": "2026-08-01",
    }, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/servicos")
    import json
    dados = json.loads(_conn(tmp_path).execute(
        "SELECT dados_json FROM propostas WHERE id=?", (pid,)).fetchone()[0])
    assert dados["duracao_meses"] == "12"


def test_etapa_local_data_invalida_reexibe_com_erro(client, tmp_path):
    pid = _nova(client)
    r = client.post(f"/propostas/{pid}/local", data={
        "descricao_local": "Empresa", "endereco_servico": "Av. Exemplo, 1000",
        "duracao_meses": "12", "data_inicio": "banana",
    })
    assert r.status_code == 200
    assert "inválid" in r.text.lower()
    import json
    dados = json.loads(_conn(tmp_path).execute(
        "SELECT dados_json FROM propostas WHERE id=?", (pid,)).fetchone()[0])
    assert dados == {}  # dados_json não foi atualizado


def test_etapa_local_duracao_nao_numerica_reexibe_com_erro(client):
    pid = _nova(client)
    r = client.post(f"/propostas/{pid}/local", data={
        "descricao_local": "Empresa", "endereco_servico": "Av. Exemplo, 1000",
        "duracao_meses": "abc", "data_inicio": "2026-08-01",
    })
    assert r.status_code == 200
    assert "inválid" in r.text.lower()


def test_etapa_local_evento_hora_invalida_reexibe_com_erro(client):
    pid = _nova(client, tipo="evento")
    r = client.post(f"/propostas/{pid}/local", data={
        "nome_evento": "Show", "endereco_servico": "Rua X, 1",
        "data_evento": "2026-08-01", "hora_inicio": "25:99", "hora_fim": "22:00",
    })
    assert r.status_code == 200
    assert "inválid" in r.text.lower()


def test_etapa_servicos_gera_linhas(client, tmp_path):
    pid = _nova(client)
    conn = _conn(tmp_path)
    noturna = conn.execute(
        "SELECT id FROM funcoes WHERE nome LIKE 'Portaria noturna%'").fetchone()["id"]
    r = client.post(f"/propostas/{pid}/servicos", data={
        "hora_inicio_turno": "18:00", "hora_fim_turno": "06:00",
        "plantoes_mes": "15", "trajes": "Fardamento padrão da empresa prestadora",
        "observacoes": "", f"qtd_{noturna}": "2",
    }, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/custos")

    linhas = conn.execute(
        "SELECT * FROM linhas_custo WHERE proposta_id=? ORDER BY ordem", (pid,)).fetchall()
    categorias = [l["categoria"] for l in linhas]
    assert categorias.count("mao_de_obra") == 1
    assert "acessorio" in categorias and "derivada" in categorias
    mo = [l for l in linhas if l["categoria"] == "mao_de_obra"][0]
    assert mo["quantidade"] == 2
    # noturna 18h-06h com seed (piso 1.600,00, divisor 220, 20%, 15 plantões):
    # 120h x (160000/220) x 0.20 = 17.454,54... -> 17455 + 160000
    assert mo["valor_sugerido_centavos"] == 177455


def test_etapa_servicos_qtd_invalida_reexibe_com_erro(client, tmp_path):
    pid = _nova(client)
    conn = _conn(tmp_path)
    noturna = conn.execute(
        "SELECT id FROM funcoes WHERE nome LIKE 'Portaria noturna%'").fetchone()["id"]
    r = client.post(f"/propostas/{pid}/servicos", data={
        "hora_inicio_turno": "18:00", "hora_fim_turno": "06:00",
        "plantoes_mes": "15", "trajes": "Fardamento padrão da empresa prestadora",
        "observacoes": "", f"qtd_{noturna}": "abc",
    })
    assert r.status_code == 200
    assert "inválid" in r.text.lower()
    linhas = conn.execute(
        "SELECT * FROM linhas_custo WHERE proposta_id=?", (pid,)).fetchall()
    assert linhas == []  # nenhuma linha criada


def test_etapa_servicos_resubmissao_preserva_override(client, tmp_path):
    pid = _nova(client)
    conn = _conn(tmp_path)
    noturna = conn.execute(
        "SELECT id FROM funcoes WHERE nome LIKE 'Portaria noturna%'").fetchone()["id"]
    dados_form = {
        "hora_inicio_turno": "18:00", "hora_fim_turno": "06:00",
        "plantoes_mes": "15", "trajes": "Fardamento padrão da empresa prestadora",
        "observacoes": "", f"qtd_{noturna}": "2",
    }
    client.post(f"/propostas/{pid}/servicos", data=dados_form, follow_redirects=False)

    linha = conn.execute(
        "SELECT * FROM linhas_custo WHERE proposta_id=? AND categoria='mao_de_obra'",
        (pid,)).fetchone()
    client.post(f"/propostas/{pid}/linhas/{linha['id']}/valor", data={"valor": "1.900,00"})

    # re-submete a mesma etapa com a mesma função, mudando a quantidade
    dados_form[f"qtd_{noturna}"] = "3"
    r = client.post(f"/propostas/{pid}/servicos", data=dados_form, follow_redirects=False)
    assert r.status_code == 303

    linhas_mo = conn.execute(
        "SELECT * FROM linhas_custo WHERE proposta_id=? AND categoria='mao_de_obra'",
        (pid,)).fetchall()
    assert len(linhas_mo) == 1  # não duplicou a linha
    linha = linhas_mo[0]
    assert linha["quantidade"] == 3
    assert linha["sobrescrito"] == 1
    assert linha["valor_final_centavos"] == 190000  # override preservado
    assert linha["valor_sugerido_centavos"] == 177455  # sugerido recalculado


def _linha_manual(conn, pid):
    return conn.execute(
        "SELECT * FROM linhas_custo WHERE proposta_id=? AND categoria='manual'",
        (pid,)).fetchall()


def test_adicionar_linha_manual(client, tmp_path):
    pid = _nova(client)
    r = client.post(f"/propostas/{pid}/linhas/nova",
                    data={"descricao": "Operacional", "valor": "208,00"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/custos")
    linhas = _linha_manual(_conn(tmp_path), pid)
    assert len(linhas) == 1
    linha = linhas[0]
    assert linha["descricao"] == "Operacional"
    assert linha["quantidade"] == 1
    assert linha["valor_final_centavos"] == 20800
    assert linha["valor_sugerido_centavos"] == 20800


def test_adicionar_linha_manual_htmx_devolve_parcial(client):
    pid = _nova(client)
    r = client.post(f"/propostas/{pid}/linhas/nova",
                    data={"descricao": "Operacional", "valor": "208,00"},
                    headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "Operacional" in r.text
    assert "<html" not in r.text  # parcial, não a página inteira


def test_linha_manual_descricao_vazia_reexibe_erro(client, tmp_path):
    pid = _nova(client)
    r = client.post(f"/propostas/{pid}/linhas/nova",
                    data={"descricao": "   ", "valor": "208,00"},
                    headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "Descrição é obrigatória" in r.text
    assert _linha_manual(_conn(tmp_path), pid) == []


def test_linha_manual_valor_ilegivel_reexibe_erro(client, tmp_path):
    pid = _nova(client)
    r = client.post(f"/propostas/{pid}/linhas/nova",
                    data={"descricao": "Operacional", "valor": "banana"},
                    headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "Valor inválido" in r.text
    assert _linha_manual(_conn(tmp_path), pid) == []


def test_remover_linha_manual(client, tmp_path):
    pid = _nova(client)
    client.post(f"/propostas/{pid}/linhas/nova",
                data={"descricao": "Operacional", "valor": "208,00"})
    conn = _conn(tmp_path)
    lid = _linha_manual(conn, pid)[0]["id"]
    r = client.post(f"/propostas/{pid}/linhas/{lid}/remover", follow_redirects=False)
    assert r.status_code == 303
    assert _linha_manual(conn, pid) == []


def test_remover_linha_nao_manual_eh_bloqueado(client, tmp_path):
    pid = _nova(client)
    conn = _conn(tmp_path)
    conn.execute(
        "INSERT INTO linhas_custo (proposta_id, descricao, categoria, quantidade,"
        " valor_sugerido_centavos, valor_final_centavos) VALUES (?, ?, ?, ?, ?, ?)",
        (pid, "Portaria diurna", "mao_de_obra", 1, 160000, 160000))
    conn.commit()
    lid = conn.execute("SELECT id FROM linhas_custo WHERE proposta_id=?", (pid,)).fetchone()["id"]
    r = client.post(f"/propostas/{pid}/linhas/{lid}/remover", follow_redirects=False)
    assert r.status_code == 404
    assert conn.execute(
        "SELECT COUNT(*) FROM linhas_custo WHERE proposta_id=?", (pid,)).fetchone()[0] == 1


def test_linha_manual_bloqueada_em_proposta_emitida(client, tmp_path):
    pid = _nova(client)
    conn = _conn(tmp_path)
    conn.execute("UPDATE propostas SET status='emitida' WHERE id=?", (pid,))
    conn.commit()
    r = client.post(f"/propostas/{pid}/linhas/nova",
                    data={"descricao": "Operacional", "valor": "208,00"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/emitida")
    assert _linha_manual(conn, pid) == []
