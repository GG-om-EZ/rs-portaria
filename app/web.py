"""Jinja compartilhado entre rotas (Jinja2Templates) e renderização fora de request."""
from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.moeda import format_brl

_DIR = Path(__file__).parent / "templates"

env = Environment(loader=FileSystemLoader(_DIR), autoescape=select_autoescape(["html"]))
env.filters["brl"] = format_brl

templates = Jinja2Templates(env=env)
