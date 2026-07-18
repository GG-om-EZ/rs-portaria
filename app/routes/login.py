import hmac
import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import assinar_sessao
from app.web import templates

router = APIRouter()


@router.get("/login")
def form_login(request: Request):
    return templates.TemplateResponse(request, "login.html", {"erro": None})


@router.post("/login")
def entrar(request: Request, pin: str = Form(...)):
    if not hmac.compare_digest(pin.encode(), os.environ["APP_PIN"].encode()):
        return templates.TemplateResponse(request, "login.html", {"erro": "PIN incorreto"})
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("sessao", assinar_sessao(os.environ["APP_SECRET"]),
                    httponly=True, samesite="lax", max_age=60 * 60 * 12)
    return resp
