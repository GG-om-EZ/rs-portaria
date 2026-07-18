from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app import repo_catalogo as rcat
from app.db import conn_dep
from app.moeda import format_brl, parse_brl
from app.web import templates

router = APIRouter(prefix="/admin")

# Chaves editáveis e seus rótulos (ordem de exibição)
CHAVES = [
    ("pct_encargos", "Encargos sociais (fração, ex.: 0.58)"),
    ("pct_noturno", "Adicional noturno (fração, ex.: 0.20)"),
    ("pct_margem", "Margem administrativa (fração, ex.: 0.10)"),
    ("divisor_horas", "Divisor de horas mensal (CLT: 220)"),
    ("plantoes_mes_padrao", "Plantões por mês (padrão 12x36)"),
    ("validade_dias", "Validade da proposta (dias)"),
    ("valor_alimentacao_continuo", "Alimentação mensal por profissional (R$)"),
    ("valor_transporte_continuo", "Transporte mensal por profissional (R$)"),
    ("valor_alimentacao_evento", "Alimentação por profissional/evento (R$)"),
    ("valor_transporte_evento", "Transporte por profissional/evento (R$)"),
    ("empresa_nome", "Razão social"), ("empresa_cnpj", "CNPJ"),
    ("empresa_endereco", "Endereço"), ("empresa_telefone", "Telefone/WhatsApp"),
    ("empresa_email", "E-mail"), ("pagamento_pix", "Chave PIX"),
    ("pagamento_banco", "Dados bancários"),
    ("condicoes_continuo", "Condições gerais — contínuo (um parágrafo por linha)"),
    ("condicoes_evento", "Condições gerais — evento (um parágrafo por linha)"),
    ("obs_finais_continuo", "Observações finais — contínuo"),
    ("obs_finais_evento", "Observações finais — evento"),
]

_MONETARIA = lambda chave: chave.startswith("valor_")
_CHAVES_VALIDAS = {c for c, _ in CHAVES}


def _render_painel(request: Request, conn, erro: str | None = None):
    parametros = []
    for chave, rotulo in CHAVES:
        valor = rcat.parametro_vigente(conn, chave) or ""
        if _MONETARIA(chave) and valor:
            valor = format_brl(int(valor))
        parametros.append({"chave": chave, "rotulo": rotulo, "valor": valor,
                           "longo": chave.startswith(("condicoes", "obs_"))})
    return templates.TemplateResponse(request, "admin.html", {
        "parametros": parametros,
        "funcoes": rcat.listar_funcoes(conn, apenas_ativas=False),
        "hoje": date.today().isoformat(),
        "erro": erro,
    })


@router.get("")
def painel(request: Request, conn=Depends(conn_dep)):
    return _render_painel(request, conn)


@router.post("/parametros")
def salvar_parametro(request: Request, chave: str = Form(...), valor: str = Form(...),
                     vigencia_inicio: str = Form(...), conn=Depends(conn_dep)):
    try:
        if chave not in _CHAVES_VALIDAS:
            raise ValueError(f"Chave desconhecida: {chave}")
        if _MONETARIA(chave):
            valor = str(parse_brl(valor))
        rcat.definir_parametro(conn, chave, valor.strip(), vigencia_inicio)
    except ValueError as exc:
        return _render_painel(request, conn, erro=str(exc))
    return RedirectResponse("/admin", status_code=303)


@router.post("/funcoes")
def criar_funcao(request: Request, nome: str = Form(...), tipo: str = Form(...),
                 valor_base: str = Form(""), aplica_noturno: str = Form(""),
                 conn=Depends(conn_dep)):
    try:
        rcat.criar_funcao(conn, nome, tipo, parse_brl(valor_base),
                          aplica_noturno=bool(aplica_noturno))
    except ValueError as exc:
        return _render_painel(request, conn, erro=str(exc))
    return RedirectResponse("/admin", status_code=303)


@router.post("/funcoes/{fid}")
def atualizar_funcao(request: Request, fid: int, valor_base: str = Form(""),
                     ativa: str = Form(""), conn=Depends(conn_dep)):
    try:
        rcat.atualizar_funcao(conn, fid, valor_base_centavos=parse_brl(valor_base),
                              ativa=int(bool(ativa)))
    except ValueError as exc:
        return _render_painel(request, conn, erro=str(exc))
    return RedirectResponse("/admin", status_code=303)
