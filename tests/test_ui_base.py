from app import db as dbmod


def _conn_do_client(tmp_path):
    c = dbmod.get_conn(tmp_path / "app.db")
    return c


def test_home_renderiza(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Nova proposta" in r.text


def test_criar_proposta_redireciona_para_wizard(client, tmp_path):
    r = client.post("/propostas/nova", data={"tipo": "continuo"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].endswith("/cliente")
    conn = _conn_do_client(tmp_path)
    assert conn.execute("SELECT COUNT(*) AS n FROM propostas").fetchone()["n"] == 1


def test_lista_e_busca(client, tmp_path):
    client.post("/propostas/nova", data={"tipo": "evento"})
    r = client.get("/propostas")
    assert r.status_code == 200 and "evento" in r.text.lower()
    assert client.get("/propostas?q=zzz-inexistente").status_code == 200


def test_duplicar(client, tmp_path):
    client.post("/propostas/nova", data={"tipo": "continuo"})
    conn = _conn_do_client(tmp_path)
    pid = conn.execute("SELECT id FROM propostas").fetchone()["id"]
    r = client.post(f"/propostas/{pid}/duplicar", follow_redirects=False)
    assert r.status_code == 303
    assert conn.execute("SELECT COUNT(*) AS n FROM propostas").fetchone()["n"] == 2
