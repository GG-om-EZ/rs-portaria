import os

os.environ.setdefault("APP_PIN", "1234")
os.environ.setdefault("APP_SECRET", "segredo-de-teste")

import pytest

from app import db as dbmod


@pytest.fixture
def conn(tmp_path):
    c = dbmod.get_conn(tmp_path / "teste.db")
    dbmod.init_db(c)
    yield c
    c.close()


def _novo_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RSP_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("RSP_ARQUIVO_DIR", str(tmp_path / "arquivo"))
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app())


@pytest.fixture
def client_sem_login(tmp_path, monkeypatch):
    return _novo_client(tmp_path, monkeypatch)


@pytest.fixture
def client(tmp_path, monkeypatch):
    tc = _novo_client(tmp_path, monkeypatch)
    tc.post("/login", data={"pin": "1234"})
    return tc
