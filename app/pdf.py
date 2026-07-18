"""Renderização do documento (preview HTML e PDF via WeasyPrint)."""
import re
from pathlib import Path

from app.web import env

_STATIC = Path(__file__).parent / "static"


def render_documento_html(snapshot: dict) -> str:
    tpl = env.get_template("documento/proposta.html")
    return tpl.render(s=snapshot, logo_uri=(_STATIC / "logo.png").as_uri())


def gerar_pdf(snapshot: dict) -> bytes:
    from weasyprint import HTML  # import tardio: app funciona sem a lib até emitir

    return HTML(string=render_documento_html(snapshot)).write_pdf()


def nome_arquivo(snapshot: dict) -> str:
    razao = re.sub(r"[/\\\n]", "-", snapshot["cliente"]["razao_social"]).strip() or "cliente"
    return f"{snapshot['numero']} - {razao}.pdf"
