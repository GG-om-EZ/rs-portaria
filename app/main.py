import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app import repo_catalogo
from app.auth import sessao_valida
from app.routes import admin, login, propostas

_LIVRES = ("/login", "/saude", "/static")


def create_app() -> FastAPI:
    app = FastAPI(title="RS Portaria — Propostas")

    conn = db.get_conn()
    db.init_db(conn)
    repo_catalogo.seed_inicial(conn)
    conn.close()

    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    @app.middleware("http")
    async def exigir_sessao(request: Request, chamar):
        caminho = request.url.path
        if not caminho.startswith(_LIVRES) and not sessao_valida(
            request.cookies.get("sessao"), os.environ["APP_SECRET"]
        ):
            return RedirectResponse("/login", status_code=303)
        return await chamar(request)

    @app.get("/saude")
    def saude():
        return {"ok": True}

    app.include_router(admin.router)
    app.include_router(login.router)
    app.include_router(propostas.router)
    return app


app = create_app()
