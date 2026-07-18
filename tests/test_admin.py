from app import db as dbmod


def _conn(tmp_path):
    return dbmod.get_conn(tmp_path / "app.db")


def test_admin_renderiza(client):
    r = client.get("/admin")
    assert r.status_code == 200 and "pct_encargos" in r.text


def test_atualizar_parametro_cria_vigencia(client, tmp_path):
    r = client.post("/admin/parametros", data={
        "chave": "pct_encargos", "valor": "0.60", "vigencia_inicio": "2027-01-01",
    }, follow_redirects=False)
    assert r.status_code == 303
    conn = _conn(tmp_path)
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM parametros WHERE chave='pct_encargos'").fetchone()["n"]
    assert n == 2  # seed + novo; histórico preservado


def test_parametro_monetario_convertido(client, tmp_path):
    client.post("/admin/parametros", data={
        "chave": "valor_alimentacao_continuo", "valor": "600,00",
        "vigencia_inicio": "2026-07-01",
    })
    conn = _conn(tmp_path)
    valor = conn.execute(
        "SELECT valor FROM parametros WHERE chave='valor_alimentacao_continuo'"
        " ORDER BY vigencia_inicio DESC LIMIT 1").fetchone()["valor"]
    assert valor == "60000"


def test_criar_e_desativar_funcao(client, tmp_path):
    r = client.post("/admin/funcoes", data={
        "nome": "Recepcionista de evento (6h)", "tipo": "evento",
        "valor_base": "150,00",
    }, follow_redirects=False)
    assert r.status_code == 303
    conn = _conn(tmp_path)
    f = conn.execute("SELECT * FROM funcoes WHERE nome LIKE 'Recepcionista%'").fetchone()
    assert f["valor_base_centavos"] == 15000 and f["aplica_noturno"] == 0

    client.post(f"/admin/funcoes/{f['id']}", data={"valor_base": "180,00", "ativa": ""})
    f = conn.execute("SELECT * FROM funcoes WHERE id=?", (f["id"],)).fetchone()
    assert f["valor_base_centavos"] == 18000 and f["ativa"] == 0


def test_parametro_monetario_malformado_reexibe_erro(client, tmp_path):
    r = client.post("/admin/parametros", data={
        "chave": "valor_alimentacao_continuo", "valor": "1,853,00",
        "vigencia_inicio": "2026-07-01",
    })
    assert r.status_code == 200 and "inválido" in r.text
    conn = _conn(tmp_path)
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM parametros WHERE chave='valor_alimentacao_continuo'"
    ).fetchone()["n"]
    assert n == 1  # só o seed; nada gravado


def test_parametro_chave_desconhecida_reexibe_erro(client, tmp_path):
    r = client.post("/admin/parametros", data={
        "chave": "chave_inexistente", "valor": "1", "vigencia_inicio": "2026-07-01",
    })
    assert r.status_code == 200 and "desconhecida" in r.text
    conn = _conn(tmp_path)
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM parametros WHERE chave='chave_inexistente'"
    ).fetchone()["n"]
    assert n == 0


def test_criar_funcao_valor_vazio_reexibe_erro(client, tmp_path):
    r = client.post("/admin/funcoes", data={
        "nome": "Vigia temporário", "tipo": "evento", "valor_base": "",
    })
    assert r.status_code == 200 and "inválido" in r.text
    conn = _conn(tmp_path)
    f = conn.execute("SELECT * FROM funcoes WHERE nome LIKE 'Vigia%'").fetchone()
    assert f is None
