from app.auth import assinar_sessao, sessao_valida


def test_assinatura_valida_e_invalida():
    assert sessao_valida(assinar_sessao("s1"), "s1") is True
    assert sessao_valida(assinar_sessao("s1"), "s2") is False
    assert sessao_valida(None, "s1") is False
    assert sessao_valida("", "s1") is False


def test_rotas_exigem_login(client_sem_login):
    r = client_sem_login.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert client_sem_login.get("/saude").status_code == 200


def test_login_com_pin(client_sem_login):
    r = client_sem_login.post("/login", data={"pin": "0000"}, follow_redirects=False)
    assert r.status_code == 200 and "PIN incorreto" in r.text

    r = client_sem_login.post("/login", data={"pin": "1234"}, follow_redirects=False)
    assert r.status_code == 303
    assert client_sem_login.get("/", follow_redirects=False).status_code != 303
