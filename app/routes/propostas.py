import os
import sqlite3
from datetime import date, time
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import checklist, emissao
from app import pdf as pdf_mod
from app import repo_catalogo as rcat
from app import repo_clientes as rcli
from app import repo_propostas as rp
from app.calc import custo_profissional_continuo
from app.db import conn_dep
from app.moeda import parse_brl
from app.web import templates

router = APIRouter()


def _proposta_ou_404(conn: sqlite3.Connection, pid: int) -> sqlite3.Row:
    prop = rp.obter_proposta(conn, pid)
    if prop is None:
        raise HTTPException(404, "Proposta não encontrada")
    return prop


ETAPAS = ["cliente", "local", "servicos", "custos", "pagamento", "revisao"]


def _ctx_wizard(prop, etapa: str) -> dict:
    return {"prop": prop, "dados": rp.dados_de(prop), "etapas": ETAPAS, "etapa": etapa}


@router.get("/")
def home(request: Request, conn=Depends(conn_dep)):
    recentes = rp.listar_propostas(conn)[:5]
    return templates.TemplateResponse(request, "home.html", {"recentes": recentes})


@router.get("/propostas")
def lista(request: Request, q: str = "", conn=Depends(conn_dep)):
    return templates.TemplateResponse(
        request, "propostas_lista.html",
        {"propostas": rp.listar_propostas(conn, q), "q": q},
    )


@router.post("/propostas/nova")
def nova(tipo: str = Form(...), conn=Depends(conn_dep)):
    if tipo not in ("continuo", "evento"):
        raise HTTPException(422, "Tipo inválido")
    pid = rp.criar_proposta(conn, tipo)
    return RedirectResponse(f"/propostas/{pid}/cliente", status_code=303)


@router.post("/propostas/{pid}/duplicar")
def duplicar(pid: int, conn=Depends(conn_dep)):
    _proposta_ou_404(conn, pid)
    novo = rp.duplicar_proposta(conn, pid)
    return RedirectResponse(f"/propostas/{novo}/cliente", status_code=303)


@router.get("/propostas/{pid}/cliente")
def etapa_cliente(request: Request, pid: int, q: str = "", conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    ctx = _ctx_wizard(prop, "cliente")
    ctx.update({"clientes": rcli.buscar_clientes(conn, q), "q": q, "erro": None})
    return templates.TemplateResponse(request, "etapa_cliente.html", ctx)


@router.post("/propostas/{pid}/cliente")
def escolher_cliente(pid: int, cliente_id: int = Form(...), conn=Depends(conn_dep)):
    _proposta_ou_404(conn, pid)
    rp.definir_cliente(conn, pid, cliente_id)
    return RedirectResponse(f"/propostas/{pid}/local", status_code=303)


@router.post("/propostas/{pid}/cliente/novo")
def criar_cliente_e_vincular(
    request: Request, pid: int,
    razao_social: str = Form(...), cnpj: str = Form(...), endereco: str = Form(...),
    email: str = Form(""), telefone: str = Form(""), conn=Depends(conn_dep),
):
    prop = _proposta_ou_404(conn, pid)
    try:
        cid = rcli.criar_cliente(conn, razao_social, cnpj, endereco, email, telefone)
    except ValueError as exc:
        ctx = _ctx_wizard(prop, "cliente")
        ctx.update({"clientes": rcli.buscar_clientes(conn), "q": "", "erro": str(exc)})
        return templates.TemplateResponse(request, "etapa_cliente.html", ctx)
    rp.definir_cliente(conn, pid, cid)
    return RedirectResponse(f"/propostas/{pid}/local", status_code=303)


@router.get("/propostas/{pid}/local")
def etapa_local(request: Request, pid: int, conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    ctx = _ctx_wizard(prop, "local")
    ctx["cliente"] = rcli.obter_cliente(conn, prop["cliente_id"]) if prop["cliente_id"] else None
    ctx["erro"] = None
    return templates.TemplateResponse(request, "etapa_local.html", ctx)


def _campos_local(tipo: str) -> list[str]:
    if tipo == "continuo":
        return ["descricao_local", "endereco_servico", "duracao_meses", "data_inicio"]
    return ["nome_evento", "endereco_servico", "data_evento", "hora_inicio", "hora_fim"]


def _erro_validacao_local(tipo: str, dados: dict) -> str | None:
    if not dados.get("endereco_servico"):
        return "Endereço é obrigatório."
    if tipo == "continuo":
        try:
            if int(dados.get("duracao_meses") or "") <= 0:
                return "Duração em meses inválida."
        except ValueError:
            return "Duração em meses inválida."
        try:
            date.fromisoformat(dados.get("data_inicio") or "")
        except ValueError:
            return "Data de início inválida."
    else:
        try:
            date.fromisoformat(dados.get("data_evento") or "")
        except ValueError:
            return "Data do evento inválida."
        for campo, rotulo in [("hora_inicio", "Horário de início"), ("hora_fim", "Horário de término")]:
            try:
                time.fromisoformat(dados.get(campo) or "")
            except ValueError:
                return f"{rotulo} inválido."
    return None


@router.post("/propostas/{pid}/local")
async def salvar_local(request: Request, pid: int, conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    form = await request.form()
    campos = _campos_local(prop["tipo"])
    dados = {c: str(form.get(c, "")).strip() for c in campos}
    erro = _erro_validacao_local(prop["tipo"], dados)
    if erro:
        ctx = _ctx_wizard(prop, "local")
        ctx["dados"] = {**ctx["dados"], **dados}
        ctx["cliente"] = rcli.obter_cliente(conn, prop["cliente_id"]) if prop["cliente_id"] else None
        ctx["erro"] = erro
        return templates.TemplateResponse(request, "etapa_local.html", ctx)
    rp.atualizar_dados(conn, pid, dados)
    return RedirectResponse(f"/propostas/{pid}/servicos", status_code=303)


def _sugerido_para(conn, prop, funcao, dados) -> int:
    """Valor sugerido de uma função conforme o tipo da proposta e o turno informado."""
    if prop["tipo"] == "evento" or not funcao["aplica_noturno"]:
        return funcao["valor_base_centavos"]
    ini = time.fromisoformat(dados.get("hora_inicio_turno", "18:00"))
    fim = time.fromisoformat(dados.get("hora_fim_turno", "06:00"))
    plantoes = int(dados.get("plantoes_mes") or rcat.param_int(conn, "plantoes_mes_padrao"))
    return custo_profissional_continuo(
        funcao["valor_base_centavos"], ini, fim, plantoes, rcat.params_vigentes(conn)
    )


def _campos_servicos(tipo: str) -> list[str]:
    if tipo == "continuo":
        return ["hora_inicio_turno", "hora_fim_turno", "plantoes_mes", "trajes", "observacoes"]
    return ["trajes", "comunicacao", "observacoes"]


def _erro_validacao_servicos(tipo: str, dados: dict) -> str | None:
    if tipo != "continuo":
        return None
    for campo, rotulo in [
        ("hora_inicio_turno", "Horário de início do turno"),
        ("hora_fim_turno", "Horário de término do turno"),
    ]:
        try:
            time.fromisoformat(dados.get(campo) or "")
        except ValueError:
            return f"{rotulo} inválido."
    plantoes = dados.get("plantoes_mes") or ""
    if plantoes:
        try:
            if int(plantoes) <= 0:
                raise ValueError
        except ValueError:
            return "Plantões por mês inválido."
    return None


def _erro_validacao_qtds(conn, tipo: str, form) -> str | None:
    for funcao in rcat.listar_funcoes(conn, tipo=tipo):
        valor = str(form.get(f"qtd_{funcao['id']}", "")).strip()
        if not valor:
            continue
        try:
            if int(valor) < 0:
                raise ValueError
        except ValueError:
            return f"Quantidade inválida para {funcao['nome']}."
    return None


@router.get("/propostas/{pid}/servicos")
def etapa_servicos(request: Request, pid: int, conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    ctx = _ctx_wizard(prop, "servicos")
    ctx["funcoes"] = rcat.listar_funcoes(conn, tipo=prop["tipo"])
    ctx["qtd_atuais"] = {
        l["funcao_id"]: l["quantidade"]
        for l in rp.linhas_da_proposta(conn, pid)
        if l["categoria"] == "mao_de_obra" and l["funcao_id"]
    }
    ctx["plantoes_padrao"] = rcat.param_int(conn, "plantoes_mes_padrao")
    ctx["erro"] = None
    return templates.TemplateResponse(request, "etapa_servicos.html", ctx)


@router.post("/propostas/{pid}/servicos")
async def salvar_servicos(request: Request, pid: int, conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    form = await request.form()
    campos = _campos_servicos(prop["tipo"])
    dados_form = {c: str(form.get(c, "")).strip() for c in campos}
    erro = (_erro_validacao_servicos(prop["tipo"], dados_form)
            or _erro_validacao_qtds(conn, prop["tipo"], form))
    if erro:
        ctx = _ctx_wizard(prop, "servicos")
        ctx["dados"] = {**ctx["dados"], **dados_form}
        ctx["funcoes"] = rcat.listar_funcoes(conn, tipo=prop["tipo"])
        ctx["qtd_atuais"] = {}
        for funcao in ctx["funcoes"]:
            bruto = form.get(f"qtd_{funcao['id']}")
            if bruto is not None:
                ctx["qtd_atuais"][funcao["id"]] = bruto
        ctx["plantoes_padrao"] = rcat.param_int(conn, "plantoes_mes_padrao")
        ctx["erro"] = erro
        return templates.TemplateResponse(request, "etapa_servicos.html", ctx)
    rp.atualizar_dados(conn, pid, dados_form)
    prop = rp.obter_proposta(conn, pid)
    dados = rp.dados_de(prop)

    # upsert por funcao_id: preserva override de linhas já existentes em vez de
    # apagar e recriar (o que perderia silenciosamente qualquer valor sobrescrito)
    linhas_mo = [l for l in rp.linhas_da_proposta(conn, pid) if l["categoria"] == "mao_de_obra"]
    existentes = {l["funcao_id"]: l for l in linhas_mo if l["funcao_id"] is not None}
    orfas = [l for l in linhas_mo if l["funcao_id"] is None]  # duplicatas antigas sem função
    vistos = set()
    for funcao in rcat.listar_funcoes(conn, tipo=prop["tipo"]):
        qtd = int(form.get(f"qtd_{funcao['id']}") or 0)
        if qtd > 0:
            vistos.add(funcao["id"])
            sugerido = _sugerido_para(conn, prop, funcao, dados)
            if funcao["id"] in existentes:
                rp.atualizar_linha_mao_de_obra(conn, existentes[funcao["id"]]["id"], qtd, sugerido)
            else:
                rp.inserir_linha(conn, pid, funcao["nome"], "mao_de_obra", qtd, sugerido,
                                 funcao_id=funcao["id"])
    for funcao_id, linha in existentes.items():
        if funcao_id not in vistos:
            rp.remover_linha(conn, linha["id"])
    for linha in orfas:
        rp.remover_linha(conn, linha["id"])

    sufixo = prop["tipo"]  # 'continuo' | 'evento'
    rp.sincronizar_acessorios(
        conn, pid,
        valor_alimentacao=rcat.param_int(conn, f"valor_alimentacao_{sufixo}"),
        valor_transporte=rcat.param_int(conn, f"valor_transporte_{sufixo}"),
    )
    rp.recalcular_derivadas(conn, pid, rcat.params_vigentes(conn))
    return RedirectResponse(f"/propostas/{pid}/custos", status_code=303)


def _arquivo_dir() -> Path:
    return Path(os.environ.get("RSP_ARQUIVO_DIR", "data/propostas-enviadas"))


def _ctx_custos(conn, prop) -> dict:
    return {
        "prop": prop,
        "linhas": rp.linhas_da_proposta(conn, prop["id"]),
        "total": rp.total_proposta(conn, prop["id"]),
    }


@router.get("/propostas/{pid}/custos")
def etapa_custos(request: Request, pid: int, conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    ctx = _ctx_wizard(prop, "custos")
    ctx.update(_ctx_custos(conn, prop))
    return templates.TemplateResponse(request, "etapa_custos.html", ctx)


def _responder_tabela(request: Request, conn, pid: int, erro: str | None = None):
    prop = _proposta_ou_404(conn, pid)
    if request.headers.get("HX-Request"):
        ctx = _ctx_custos(conn, prop)
        ctx["erro"] = erro
        return templates.TemplateResponse(request, "_tabela_custos.html", ctx)
    return RedirectResponse(f"/propostas/{pid}/custos", status_code=303)


def _linha_da_proposta_ou_404(conn: sqlite3.Connection, pid: int, lid: int) -> None:
    """Garante que a linha existe e pertence à proposta indicada."""
    row = conn.execute(
        "SELECT proposta_id FROM linhas_custo WHERE id = ?", (lid,)).fetchone()
    if row is None or row["proposta_id"] != pid:
        raise HTTPException(404, "Linha não encontrada nesta proposta")


@router.post("/propostas/{pid}/linhas/{lid}/valor")
def alterar_valor(request: Request, pid: int, lid: int,
                  valor: str = Form(...), conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    if prop["status"] != "rascunho":
        return RedirectResponse(f"/propostas/{pid}/emitida", status_code=303)
    _linha_da_proposta_ou_404(conn, pid, lid)
    try:
        centavos = parse_brl(valor)
    except ValueError:
        centavos = None  # valor ilegível: mantém como está; tabela devolvida mostra o atual
    if centavos is not None:
        rp.sobrescrever_linha(conn, lid, centavos)
    rp.recalcular_derivadas(conn, pid, rcat.params_vigentes(conn))
    return _responder_tabela(request, conn, pid)


@router.post("/propostas/{pid}/linhas/{lid}/restaurar")
def restaurar_valor(request: Request, pid: int, lid: int, conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    if prop["status"] != "rascunho":
        return RedirectResponse(f"/propostas/{pid}/emitida", status_code=303)
    _linha_da_proposta_ou_404(conn, pid, lid)
    rp.restaurar_linha(conn, lid)
    rp.recalcular_derivadas(conn, pid, rcat.params_vigentes(conn))
    return _responder_tabela(request, conn, pid)


@router.post("/propostas/{pid}/linhas/nova")
def adicionar_linha_manual(request: Request, pid: int,
                           descricao: str = Form(""), valor: str = Form(""),
                           conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    if prop["status"] != "rascunho":
        return RedirectResponse(f"/propostas/{pid}/emitida", status_code=303)
    descricao = descricao.strip()
    if not descricao:
        return _responder_tabela(request, conn, pid, erro="Descrição é obrigatória.")
    try:
        centavos = parse_brl(valor)
    except ValueError:
        return _responder_tabela(request, conn, pid,
                                 erro="Valor inválido — use o formato 1.234,56.")
    rp.inserir_linha(conn, pid, descricao, "manual", 1, centavos)
    return _responder_tabela(request, conn, pid)


@router.post("/propostas/{pid}/linhas/{lid}/remover")
def remover_linha_manual(request: Request, pid: int, lid: int, conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    if prop["status"] != "rascunho":
        return RedirectResponse(f"/propostas/{pid}/emitida", status_code=303)
    linha = conn.execute(
        "SELECT proposta_id, categoria FROM linhas_custo WHERE id = ?", (lid,)).fetchone()
    # Só linhas manuais são removíveis aqui: mão de obra sai pela etapa Serviços;
    # acessórios e derivadas são geridas pelo motor
    if linha is None or linha["proposta_id"] != pid or linha["categoria"] != "manual":
        raise HTTPException(404, "Linha não encontrada nesta proposta")
    rp.remover_linha(conn, lid)
    return _responder_tabela(request, conn, pid)


@router.get("/propostas/{pid}/pagamento")
def etapa_pagamento(request: Request, pid: int, conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    return templates.TemplateResponse(request, "etapa_pagamento.html",
                                      _ctx_wizard(prop, "pagamento"))


@router.post("/propostas/{pid}/pagamento")
async def salvar_pagamento(request: Request, pid: int, conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    form = await request.form()
    novos = {"formas_pagamento": ", ".join(form.getlist("formas_pagamento"))}
    if prop["tipo"] == "continuo":
        novos["vencimento"] = str(form.get("vencimento", "")).strip()
        novos["parcela_ingresso"] = "sim" if form.get("parcela_ingresso") else ""
    else:
        novos["data_limite_pagamento"] = str(form.get("data_limite_pagamento", "")).strip()
    rp.atualizar_dados(conn, pid, novos)
    return RedirectResponse(f"/propostas/{pid}/revisao", status_code=303)


@router.get("/propostas/{pid}/revisao")
def etapa_revisao(request: Request, pid: int, conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    itens = checklist.avaliar(conn, pid)
    ctx = _ctx_wizard(prop, "revisao")
    ctx.update({"itens": itens, "pode": checklist.pode_emitir(itens),
                "total": rp.total_proposta(conn, pid), "erro": None})
    return templates.TemplateResponse(request, "etapa_revisao.html", ctx)


@router.get("/propostas/{pid}/preview")
def preview(pid: int, conn=Depends(conn_dep)):
    _proposta_ou_404(conn, pid)
    return HTMLResponse(pdf_mod.render_documento_html(emissao.montar_snapshot(conn, pid)))


@router.post("/propostas/{pid}/emitir")
def emitir(request: Request, pid: int, conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    try:
        emissao.emitir(conn, pid, _arquivo_dir())
    except ValueError as exc:  # checklist pendente
        itens = checklist.avaliar(conn, pid)
        ctx = _ctx_wizard(prop, "revisao")
        ctx.update({"itens": itens, "pode": False,
                    "total": rp.total_proposta(conn, pid), "erro": str(exc)})
        return templates.TemplateResponse(request, "etapa_revisao.html", ctx)
    except Exception:
        itens = checklist.avaliar(conn, pid)
        ctx = _ctx_wizard(prop, "revisao")
        ctx.update({"itens": itens, "pode": checklist.pode_emitir(itens),
                    "total": rp.total_proposta(conn, pid),
                    "erro": "Falha ao gerar o PDF. O rascunho foi preservado — tente novamente."})
        return templates.TemplateResponse(request, "etapa_revisao.html", ctx)
    return RedirectResponse(f"/propostas/{pid}/emitida", status_code=303)


@router.get("/propostas/{pid}/emitida")
def emitida(request: Request, pid: int, conn=Depends(conn_dep)):
    prop = _proposta_ou_404(conn, pid)
    return templates.TemplateResponse(request, "emitida.html", {"prop": prop})


@router.get("/propostas/{pid}/pdf")
def baixar_pdf(pid: int, conn=Depends(conn_dep)):
    import json as _json

    prop = _proposta_ou_404(conn, pid)
    if prop["snapshot_json"]:
        snapshot = _json.loads(prop["snapshot_json"])
    else:
        snapshot = emissao.montar_snapshot(conn, pid)
    corpo = pdf_mod.gerar_pdf(snapshot)
    nome = pdf_mod.nome_arquivo(snapshot)
    return Response(corpo, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.post("/rearquivar")
def rearquivar(conn=Depends(conn_dep)):
    emissao.rearquivar_pendentes(conn, _arquivo_dir())
    return RedirectResponse("/propostas", status_code=303)
