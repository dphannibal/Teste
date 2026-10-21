"""Agenda, calendário e cadastro de licitações."""
import calendar
import json
import re
from datetime import date, datetime, timedelta

from flask import (
    Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for,
)

from . import equipe, feriados, imagem
from . import parametros as P
from .auth import login_obrigatorio, permissao
from .db import get_db, registrar
from .perfis import (
    COLUNAS, COLUNAS_PADRAO, EQUIPE_OBRIGATORIA, FASES_ABERTAS, FASES_ANTES_DA_SESSAO,
    FASES_CREDENCIAMENTO, FASES_DA_ACAO, FASES_EM_ANDAMENTO, FUNCOES_EQUIPE,
    OCORRENCIAS, PRAZO_CONTRARRAZOES, PRAZO_DECISAO, PRAZO_RAZOES, PRAZO_RECONSIDERACAO,
    PRAZOS, VINCULOS_EFETIVOS,
)

RECURSO = "recurso"  # situação do sistema enquanto corre um recurso
RESULTADOS_RECURSO = ["Não provido", "Provido", "Parcialmente provido", "Desistência"]

bp = Blueprint("agenda", __name__)

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

EQUIPE = equipe.EQUIPE

CAMPOS = ["numero_processo", "numero_edital", "modalidade", "objeto", "data_publicacao",
          "data_sessao", "vigencia_ate", "local", *EQUIPE, "valor_estimado", "status",
          "prazo_hipotese", "observacoes"]

ROTULOS = {
    "numero_processo": "Nº do processo",
    "numero_edital": "Nº do edital",
    "modalidade": "Modalidade",
    "objeto": "Objeto",
    "data_publicacao": "Publicação",
    "data_sessao": "Data da sessão",
    "vigencia_ate": "Vigência até",
    "local": "Local / plataforma",
    **FUNCOES_EQUIPE,
    "valor_estimado": "Valor estimado",
    "status": "Situação",
    "prazo_hipotese": "Prazo mínimo",
    "observacoes": "Observações",
}

CONSULTA_BASE = """
    SELECT l.*,
           a.nome AS agente_nome, m1.nome AS membro1_nome, m2.nome AS membro2_nome,
           m3.nome AS membro3_nome, r.recurso_id, r.intimado_em, r.razoes_ate,
           r.contrarrazoes_ate, r.reconsideracao_ate, r.decisao_ate
      FROM licitacoes l
      LEFT JOIN servidores a  ON a.id  = l.agente_id
      LEFT JOIN servidores m1 ON m1.id = l.membro1_id
      LEFT JOIN servidores m2 ON m2.id = l.membro2_id
      LEFT JOIN servidores m3 ON m3.id = l.membro3_id
      LEFT JOIN (SELECT id AS recurso_id, licitacao_id, intimado_em, razoes_ate,
                        contrarrazoes_ate, reconsideracao_ate, decisao_ate
                   FROM recursos WHERE decidido_em IS NULL) r ON r.licitacao_id = l.id
"""


def situacao(lic):
    """Situação por extenso, distinguindo as fases de suspensão e remarcação."""
    nome, fase = P.situacao(lic["status"])["nome"], P.fase(lic["status"])
    if fase == "suspensa":
        return f"{nome} — sessão não aberta"
    if fase == "remarcada" and lic["ocorrencia"] == "remarcada_retificacao":
        return f"{nome} — edital retificado"
    if lic["status"] == RECURSO and lic["razoes_ate"]:
        return f"{nome} — {etapa_recurso(lic)[0].lower()}"
    if fase == "andamento" and lic["suspensa_em"]:
        return f"{nome} — suspensa p/ análise documental"
    if fase == "andamento" and lic["ocorrencia"] == "continuacao":
        return f"{nome} — continuação"
    return nome


identificacao = P.edital


def etapa_recurso(lic):
    """(etapa atual, prazo da etapa, vencido?) de um recurso em curso."""
    hoje = date.today().isoformat()
    for rotulo, campo in (("Razões", "razoes_ate"), ("Contrarrazões", "contrarrazoes_ate"),
                          ("Reconsideração", "reconsideracao_ate"),
                          ("Decisão superior", "decisao_ate")):
        if hoje <= lic[campo]:
            return rotulo, lic[campo], False
    return "Decisão superior", lic["decisao_ate"], True


def prazos_recurso(intimado_em, notificado_em=None):
    """Sugestão dos prazos do art. 165, em dias úteis, a partir da intimação/ata. As
    contrarrazões contam do fim das razões ou, se informada, da notificação das empresas."""
    razoes = feriados.contar_dias_uteis(intimado_em, PRAZO_RAZOES)
    contrarrazoes = feriados.contar_dias_uteis(notificado_em or razoes, PRAZO_CONTRARRAZOES)
    reconsideracao = feriados.contar_dias_uteis(contrarrazoes, PRAZO_RECONSIDERACAO)
    decisao = feriados.contar_dias_uteis(reconsideracao, PRAZO_DECISAO)
    return {"razoes_ate": razoes.isoformat(), "contrarrazoes_ate": contrarrazoes.isoformat(),
            "reconsideracao_ate": reconsideracao.isoformat(), "decisao_ate": decisao.isoformat()}


def _buscar(id_):
    lic = get_db().execute(CONSULTA_BASE + " WHERE l.id = ?", (id_,)).fetchone()
    if lic is None:
        abort(404)
    return lic


def _em(lista):
    return ",".join("?" * len(lista))


def somar_um_ano(dia):
    try:
        return dia.replace(year=dia.year + 1)
    except ValueError:  # 29 de fevereiro
        return dia.replace(year=dia.year + 1, day=28)


def _ler_valor(texto):
    """Aceita '1.234,56', '1234,56' ou '1234.56'."""
    texto = texto.strip().replace("R$", "").replace(" ", "")
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return round(float(texto), 2)


def _ler_data(texto, com_hora):
    """Normaliza para 'AAAA-MM-DD' ou 'AAAA-MM-DDTHH:MM'; ValueError se inválida."""
    dt = datetime.fromisoformat(texto)
    return dt.strftime("%Y-%m-%dT%H:%M" if com_hora else "%Y-%m-%d")


def prazos_da_modalidade(modalidade):
    """Objetos/critérios de julgamento cabíveis na modalidade (definem o prazo mínimo)."""
    permitidos = [p for p in (modalidade.get("prazos_permitidos") or "").split(",") if p in PRAZOS]
    return permitidos or [modalidade.get("prazo_padrao") or "nao_se_aplica"]


def criticar_sessao(dia_hora, divulgacao, prazo, confirmar_ponto):
    """Crítica da data da sessão: fim de semana, feriado, ponto facultativo e prazo mínimo
    legal contado da divulgação do edital. Retorna (erros, pontos facultativos a confirmar)."""
    dia = date.fromisoformat(dia_hora[:10])
    erros, pontos = feriados.criticar_data(dia)
    if pontos and confirmar_ponto:
        pontos = []
    erros += [f"{p} Confirme se haverá expediente para manter a data." for p in pontos]
    descricao, dias, conta_divulgacao = PRAZOS.get(prazo, PRAZOS["nao_se_aplica"])
    if dias:
        if not divulgacao:
            erros.append("Informe a data de publicação do edital para conferir o prazo mínimo "
                         "legal.")
        else:
            base = date.fromisoformat(divulgacao)
            minima = feriados.data_minima_sessao(base, dias, conta_divulgacao)
            if dia < minima:
                erros.append(
                    f"Prazo mínimo legal não respeitado: {descricao} exige {dias} dias úteis. "
                    f"Com divulgação em {base:%d/%m/%Y}, a sessão pode ocorrer a partir de "
                    f"{minima:%d/%m/%Y}.")
    return erros, pontos


def _validar(form, atual=None):
    """Retorna (dados, erros, impedidos pendentes de decisão, pontos facultativos)."""
    dados = {c: form.get(c, "").strip() for c in CAMPOS}
    erros = []

    for campo in ("numero_processo", "objeto"):
        if not dados[campo]:
            erros.append(f"Informe o campo “{ROTULOS[campo]}”.")

    validas = {m["nome"] for m in P.modalidades(True, atual and atual["modalidade"])}
    if dados["modalidade"] not in validas:
        erros.append("Selecione uma modalidade válida.")
    modalidade = P.modalidade(dados["modalidade"])
    credenciamento = bool(modalidade["credenciamento"])

    situacoes = {s["chave"] for s in P.situacoes(True, atual and atual["status"])}
    fase = P.fase(dados["status"])
    if dados["status"] not in situacoes:
        erros.append("Selecione uma situação válida.")
    elif credenciamento and fase not in FASES_CREDENCIAMENTO:
        erros.append(f"{modalidade['nome']} só pode estar em andamento ou concluído(a).")
    elif fase in FASES_DA_ACAO and (atual is None or atual["status"] != dados["status"]):
        erros.append("Para suspender ou remarcar a sessão, use o botão “Suspender / remarcar”.")
    elif dados["status"] == RECURSO and (atual is None or atual["status"] != RECURSO):
        erros.append("Para registrar recurso, use o botão “Registrar recurso”.")
    elif atual is not None and atual["status"] == RECURSO and dados["status"] != RECURSO:
        erros.append("A licitação está em recurso: registre a decisão do recurso para mudar a "
                     "situação.")

    # O edital é digitado só com o número; a sigla vem da modalidade nas visualizações.
    if modalidade["sigla"]:
        dados["numero_edital"] = re.sub(rf"^{re.escape(modalidade['sigla'])}\s+", "",
                                        dados["numero_edital"], flags=re.IGNORECASE)
    if dados["numero_edital"] and not dados["numero_edital"][0].isdigit():
        erros.append("Digite só o número do edital, sem a sigla (ex.: 007/2026).")
    elif not dados["numero_edital"] and fase != "planejamento":
        erros.append("Informe o número do edital (ex.: 007/2026).")

    for campo, com_hora in (("data_publicacao", False), ("data_sessao", True),
                            ("vigencia_ate", False)):
        if dados[campo]:
            try:
                dados[campo] = _ler_data(dados[campo], com_hora)
            except ValueError:
                erros.append(f"{ROTULOS[campo]}: data inválida.")
                dados[campo] = None
        else:
            dados[campo] = None

    if credenciamento:
        # Aberto indefinidamente: não há sessão, há vigência renovada a cada ano.
        dados["data_sessao"] = None
        if not dados["data_publicacao"]:
            erros.append("Informe a data de publicação do edital de credenciamento.")
        elif not dados["vigencia_ate"]:
            dados["vigencia_ate"] = somar_um_ano(
                date.fromisoformat(dados["data_publicacao"])).isoformat()
        elif dados["vigencia_ate"] <= dados["data_publicacao"]:
            erros.append("A vigência deve terminar depois da publicação.")
    else:
        dados["vigencia_ate"] = None
        if not dados["data_sessao"] and fase != "planejamento":
            erros.append("Informe a data e a hora da sessão.")
        if (dados["data_sessao"] and dados["data_publicacao"]
                and dados["data_sessao"][:10] < dados["data_publicacao"]):
            erros.append("A sessão não pode ser anterior à publicação do edital.")

    # Enquadramento do prazo mínimo legal (o padrão vem da modalidade).
    if credenciamento:
        dados["prazo_hipotese"] = "nao_se_aplica"
    dados["prazo_hipotese"] = dados["prazo_hipotese"] or modalidade.get("prazo_padrao")
    if dados["prazo_hipotese"] not in prazos_da_modalidade(modalidade):
        erros.append(f"O objeto/critério de julgamento escolhido não cabe na modalidade "
                     f"{modalidade['nome']}.")
        dados["prazo_hipotese"] = modalidade.get("prazo_padrao") or "nao_se_aplica"

    # A data só é criticada quando muda (ou quando o edital é publicado), para não travar a
    # edição de licitações antigas.
    pontos = []
    publicando = atual is not None and P.fase(atual["status"]) == "planejamento"
    mudou = atual is None or publicando or any(
        atual[c] != dados[c] for c in ("data_sessao", "data_publicacao")) or (
        atual["prazo_hipotese"] is not None
        and atual["prazo_hipotese"] != dados["prazo_hipotese"])
    if dados["data_sessao"] and fase != "planejamento" and mudou:
        divulgacao = (atual["retificado_em"] if atual else None) or dados["data_publicacao"]
        erros_data, pontos = criticar_sessao(
            dados["data_sessao"], divulgacao, dados["prazo_hipotese"],
            bool(form.get("confirmar_ponto_facultativo")))
        erros += erros_data

    try:
        dados["valor_estimado"] = _ler_valor(dados["valor_estimado"])
        if dados["valor_estimado"] is not None and dados["valor_estimado"] < 0:
            erros.append("O valor estimado não pode ser negativo.")
    except ValueError:
        erros.append("Valor estimado inválido. Use, por exemplo, 150.000,00.")

    servidores = equipe.servidores([atual[c] for c in EQUIPE] if atual else [])
    validos = {s["id"] for s in servidores}
    for campo in EQUIPE:
        valor = dados[campo]
        dados[campo] = int(valor) if valor.isdigit() and int(valor) in validos else None
        if valor and dados[campo] is None:
            erros.append(f"{ROTULOS[campo]}: servidor inválido.")

    ids = [dados[c] for c in EQUIPE if dados[c]]
    if (fase != "planejamento" and modalidade["exige_equipe"]
            and not all(dados[c] for c in EQUIPE_OBRIGATORIA)):
        erros.append("Informe a equipe: pregoeiro / agente de contratação e dois membros.")
    erros += equipe.problemas(ids, servidores)

    mantidos = equipe.ler_mantidos(atual["impedimentos_mantidos"] if atual else "")
    erros_imp, pendentes, mantidos = equipe.verificar(
        ids, dados["data_sessao"], fase == "andamento", mantidos,
        manter=bool(form.get("manter_impedidos")),
    )
    erros += erros_imp
    dados["impedimentos_mantidos"] = ",".join(map(str, sorted(mantidos))) or None

    for campo in ("numero_edital", "local", "observacoes"):
        dados[campo] = dados[campo] or None

    return dados, erros, pendentes, pontos


# --- Colunas e ordenação escolhidas por usuário ------------------------------------------

def _chave_edital(lic):
    """Ordena 007/2026 por ano e depois pelo número."""
    numero = lic["numero_edital"] or ""
    achado = re.match(r"\D*(\d+)\D+(\d{4})", numero)
    if achado:
        return (int(achado.group(2)), int(achado.group(1)), numero)
    return (9999, 0, numero or lic["numero_processo"])


CRITERIOS = {
    "edital": _chave_edital,
    "data": lambda l: l["data_sessao"] or l["vigencia_ate"] or "9999",
    "modalidade": lambda l: (P.modalidade(l["modalidade"])["ordem"], l["modalidade"]),
    "objeto": lambda l: l["objeto"].lower(),
    "equipe": lambda l: (l["agente_nome"] or "~").lower(),
    "situacao": lambda l: P.situacao(l["status"])["ordem"],
    "local": lambda l: (l["local"] or "~").lower(),
    "valor": lambda l: l["valor_estimado"] if l["valor_estimado"] is not None else -1,
    "publicacao": lambda l: l["data_publicacao"] or "",
}


def preferencias():
    """Colunas visíveis (na ordem escolhida) e ordenação do usuário logado."""
    if "preferencias" not in g:
        try:
            salvas = json.loads(g.usuario["preferencias"] or "{}")
        except (TypeError, ValueError):
            salvas = {}
        colunas = [c for c in salvas.get("colunas", []) if c in COLUNAS] or COLUNAS_PADRAO
        g.preferencias = {
            "colunas": colunas,
            "ordem": salvas.get("ordem") if salvas.get("ordem") in CRITERIOS else "data",
            "direcao": "desc" if salvas.get("direcao") == "desc" else "asc",
        }
    return g.preferencias


def _salvar_preferencias(prefs):
    get_db().execute("UPDATE usuarios SET preferencias = ? WHERE id = ?",
                     (json.dumps(prefs), g.usuario["id"]))
    get_db().commit()
    g.preferencias = prefs


def _ordenacao_da_url():
    """Clique no título da coluna: ordena e guarda a escolha para as próximas visitas."""
    prefs = preferencias()
    ordem, direcao = request.args.get("ordem"), request.args.get("dir")
    if ordem in CRITERIOS and (ordem, direcao) != (prefs["ordem"], prefs["direcao"]):
        _salvar_preferencias({**prefs, "ordem": ordem,
                              "direcao": "desc" if direcao == "desc" else "asc"})
    return preferencias()


def ordenar(licitacoes):
    prefs = preferencias()
    return sorted(licitacoes, key=CRITERIOS[prefs["ordem"]], reverse=prefs["direcao"] == "desc")


def link_ordem(coluna):
    prefs = preferencias()
    direcao = "desc" if prefs["ordem"] == coluna and prefs["direcao"] == "asc" else "asc"
    args = {**request.args.to_dict(), "ordem": coluna, "dir": direcao}
    return url_for(request.endpoint, **(request.view_args or {}), **args)


@bp.route("/preferencias/tabela", methods=["POST"])
@login_obrigatorio
def salvar_tabela():
    visiveis = set(request.form.getlist("visivel"))
    colunas = [c for c in request.form.getlist("coluna") if c in COLUNAS and c in visiveis]
    prefs = {
        "colunas": colunas or COLUNAS_PADRAO,
        "ordem": request.form.get("ordem") if request.form.get("ordem") in CRITERIOS else "data",
        "direcao": "desc" if request.form.get("direcao") == "desc" else "asc",
    }
    _salvar_preferencias(prefs)
    flash("Colunas e ordenação salvas.", "sucesso")
    voltar = request.form.get("voltar", "")
    return redirect(voltar if voltar.startswith("/") and not voltar.startswith("//")
                    else url_for("agenda.painel"))


@bp.app_context_processor
def _globais():
    usuario = g.get("usuario")
    return {
        "situacao": situacao,
        "OCORRENCIAS": OCORRENCIAS,
        "COLUNAS": COLUNAS,
        "link_ordem": link_ordem,
        "preferencias": preferencias if usuario else (lambda: None),
        "CRITERIOS": CRITERIOS,
    }


# --- Telas -------------------------------------------------------------------------------

def _filtrar(args):
    """Monta a cláusula WHERE a partir dos filtros da listagem."""
    condicoes, params = [], []
    termo = args.get("q", "").strip()
    if termo:
        busca = ["l.objeto LIKE ?", "l.numero_processo LIKE ?", "l.numero_edital LIKE ?"]
        params += [f"%{termo}%"] * 3
        # "PE 007" procura o edital 007 nas modalidades de sigla PE.
        partes = termo.split(None, 1)
        siglas = [m["nome"] for m in P.modalidades() if m["sigla"].lower() == partes[0].lower()]
        if siglas:
            busca.append(f"(l.modalidade IN ({_em(siglas)}) AND l.numero_edital LIKE ?)")
            params += [*siglas, f"{partes[1] if len(partes) > 1 else ''}%"]
        condicoes.append("(" + " OR ".join(busca) + ")")
    if args.get("modalidade"):
        condicoes.append("l.modalidade = ?")
        params.append(args["modalidade"])
    if args.get("status"):
        condicoes.append("l.status = ?")
        params.append(args["status"])
    if args.get("servidor", "").isdigit():
        condicoes.append("? IN (l.agente_id, l.membro1_id, l.membro2_id, l.membro3_id)")
        params.append(int(args["servidor"]))
    if args.get("de"):
        condicoes.append("l.data_sessao >= ?")
        params.append(args["de"])
    if args.get("ate"):
        condicoes.append("l.data_sessao < ?")
        params.append(args["ate"] + "T99")  # inclui o dia inteiro
    where = (" WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return where, params


def _por_fases(*fases):
    chaves = P.chaves(*fases)
    return get_db().execute(
        CONSULTA_BASE + f" WHERE l.status IN ({_em(chaves)})", chaves).fetchall()


@bp.route("/")
@permissao("ver")
def painel():
    _ordenacao_da_url()
    agora = datetime.now().strftime("%Y-%m-%dT%H:%M")
    hoje = date.today()

    # Licitações em andamento: publicadas, remarcadas e com sessão aberta, inclusive as
    # suspensas depois de abertas. O credenciamento tem quadro próprio.
    em_andamento = ordenar([l for l in _por_fases(*FASES_EM_ANDAMENTO)
                            if not P.eh_credenciamento(l["modalidade"]) and not l["recurso_id"]])
    em_recurso = sorted((l for l in _por_fases("andamento") if l["recurso_id"]),
                        key=lambda l: etapa_recurso(l)[1])
    sessoes_hoje = sorted((l for l in em_andamento if not l["suspensa_em"] and l["data_sessao"]
                           and l["data_sessao"].startswith(hoje.isoformat())),
                          key=lambda l: l["data_sessao"])
    suspensas = ordenar(_por_fases("suspensa"))
    credenciamentos = sorted((l for l in _por_fases("andamento")
                              if P.eh_credenciamento(l["modalidade"])),
                             key=lambda l: l["vigencia_ate"] or "")
    contagem = dict(get_db().execute(
        "SELECT status, COUNT(*) FROM licitacoes GROUP BY status").fetchall())
    modalidades_em_uso = sorted({l["modalidade"] for l in (*em_andamento, *suspensas)},
                                key=lambda m: P.modalidade(m)["ordem"])

    return render_template(
        "agenda/painel.html", em_andamento=em_andamento, sessoes_hoje=sessoes_hoje,
        em_recurso=em_recurso, etapa_recurso=etapa_recurso,
        suspensas=suspensas, credenciamentos=credenciamentos, contagem=contagem,
        situacoes=P.situacoes(), agora=agora, hoje=hoje.isoformat(),
        alerta_renovacao=(hoje + timedelta(days=30)).isoformat(),
        modalidades_em_uso=modalidades_em_uso,
    )


@bp.route("/calendario")
@permissao("ver")
def calendario():
    hoje = date.today()
    try:
        ano = int(request.args.get("ano", hoje.year))
        mes = int(request.args.get("mes", hoje.month))
        date(ano, mes, 1)
    except ValueError:
        ano, mes = hoje.year, hoje.month

    semanas = calendar.Calendar(firstweekday=6).monthdatescalendar(ano, mes)
    inicio, fim = semanas[0][0].isoformat(), (semanas[-1][-1] + timedelta(days=1)).isoformat()
    credenciamentos = [m["nome"] for m in P.modalidades() if m["credenciamento"]] or [""]
    andamento = P.chaves("andamento")
    nao_uteis = {}
    for ano_ in {semanas[0][0].year, semanas[-1][-1].year}:
        for dia, lista in feriados.ocorrencias(ano_).items():
            nao_uteis.setdefault(dia.isoformat(), []).extend(lista)
    eventos = {}
    for lic in get_db().execute(
        CONSULTA_BASE + " WHERE (l.data_sessao >= ? AND l.data_sessao < ?)"
        f" OR (l.modalidade IN ({_em(credenciamentos)}) AND l.status IN ({_em(andamento)})"
        "     AND l.vigencia_ate >= ? AND l.vigencia_ate < ?)"
        " ORDER BY l.data_sessao",
        (inicio, fim, *credenciamentos, *andamento, inicio, fim),
    ):
        if P.eh_credenciamento(lic["modalidade"]):
            dia, rotulo = lic["vigencia_ate"], f"Renovar {identificacao(lic)}"
        else:
            dia = lic["data_sessao"][:10]
            rotulo = f"{lic['data_sessao'][11:16]} {identificacao(lic)}"
        eventos.setdefault(dia, []).append({"lic": lic, "rotulo": rotulo})

    anterior = date(ano, mes, 1) - timedelta(days=1)
    seguinte = date(ano, mes, 28) + timedelta(days=7)
    return render_template(
        "agenda/calendario.html",
        semanas=semanas, eventos=eventos, ano=ano, mes=mes, nome_mes=MESES[mes - 1],
        hoje=hoje, anterior=anterior, seguinte=seguinte, modalidades=P.modalidades(True),
        nao_uteis=nao_uteis,
        situacoes=P.situacoes(True),
    )


@bp.route("/licitacoes")
@permissao("ver")
def lista():
    _ordenacao_da_url()
    where, params = _filtrar(request.args)
    licitacoes = ordenar(get_db().execute(CONSULTA_BASE + where, params).fetchall())
    return render_template(
        "agenda/lista.html", licitacoes=licitacoes, modalidades=P.modalidades(),
        situacoes=P.situacoes(), servidores=equipe.servidores(), filtros=request.args,
        agora=datetime.now().strftime("%Y-%m-%dT%H:%M"),
    )


def _render_form(dados, titulo, atual=None, pendentes=(), pontos=()):
    situacoes = [s for s in P.situacoes(True, atual and atual["status"])
                 if (s["fase"] not in FASES_DA_ACAO and s["chave"] != RECURSO)
                 or (atual and atual["status"] == s["chave"])]
    return render_template(
        "agenda/form.html", dados=dados, titulo=titulo, atual=atual, pendentes=pendentes,
        pontos=pontos, prazos=PRAZOS, prazos_da_modalidade=prazos_da_modalidade,
        nao_uteis=feriados.dias_nao_uteis(date.today() - timedelta(days=60),
                                          date.today() + timedelta(days=730)),
        modalidades=P.modalidades(True, atual and atual["modalidade"]), situacoes=situacoes,
        servidores=equipe.servidores([dados.get(c) for c in EQUIPE]),
        fases_credenciamento=FASES_CREDENCIAMENTO, efetivos=VINCULOS_EFETIVOS,
        funcoes=FUNCOES_EQUIPE,
    )


@bp.route("/licitacoes/nova", methods=["GET", "POST"])
@permissao("criar")
def nova():
    dados = {"status": P.chaves("planejamento")[0]}
    pendentes = pontos = []
    if request.method == "POST":
        dados, erros, pendentes, pontos = _validar(request.form)
        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            conn = get_db()
            colunas = [*CAMPOS, "impedimentos_mantidos"]
            cur = conn.execute(
                f"INSERT INTO licitacoes ({', '.join(colunas)}, criado_por)"
                f" VALUES ({_em(colunas)}, ?)",
                (*[dados[c] for c in colunas], g.usuario["id"]),
            )
            registrar("Cadastro de licitação", referencia=identificacao(dados),
                      licitacao_id=cur.lastrowid)
            conn.commit()
            flash("Licitação cadastrada.", "sucesso")
            return redirect(url_for("agenda.detalhe", id_=cur.lastrowid))

    return _render_form(dados, "Nova licitação", pendentes=pendentes, pontos=pontos)


@bp.route("/licitacoes/<int:id_>")
@permissao("ver")
def detalhe(id_):
    lic = _buscar(id_)
    historico = get_db().execute(
        "SELECT h.*, u.nome AS usuario_nome FROM historico h"
        " LEFT JOIN usuarios u ON u.id = h.usuario_id"
        " WHERE h.licitacao_id = ? ORDER BY h.id DESC",
        (id_,),
    ).fetchall()
    ids = [lic[c] for c in EQUIPE]
    escalados = {s["id"]: s for s in equipe.servidores(ids)}
    fase = P.fase(lic["status"])
    # A escala pode ter ficado irregular depois (mudança de vínculo, férias lançadas...).
    alertas = equipe.problemas([i for i in ids if i], list(escalados.values()))
    if fase in FASES_ABERTAS and fase != "suspensa":
        alertas += equipe.verificar(
            ids, lic["data_sessao"], fase == "andamento",
            equipe.ler_mantidos(lic["impedimentos_mantidos"]), manter=False)[0]
    chave_prazo = lic["prazo_hipotese"] or P.modalidade(lic["modalidade"])["prazo_padrao"]
    descricao_prazo, dias_prazo, conta = PRAZOS.get(chave_prazo, PRAZOS["nao_se_aplica"])
    divulgacao = lic["retificado_em"] or lic["data_publicacao"]
    minima = (feriados.data_minima_sessao(date.fromisoformat(divulgacao), dias_prazo, conta)
              if divulgacao and dias_prazo else None)
    recursos = get_db().execute("SELECT * FROM recursos WHERE licitacao_id = ? ORDER BY id DESC",
                                (id_,)).fetchall()
    if lic["data_sessao"] and fase in FASES_ABERTAS:
        motivos = feriados.motivos(date.fromisoformat(lic["data_sessao"][:10]))
        alertas += [f"A data da sessão é {_minuscula(feriados.descrever(m))}." for m in motivos]
    return render_template(
        "agenda/detalhe.html", lic=lic, historico=historico, escalados=escalados,
        prazo=(descricao_prazo, dias_prazo), data_minima=minima, recursos=recursos,
        pode_recorrer=_pode_recorrer(lic), etapa_recurso=etapa_recurso,
        alertas_equipe=alertas, credenciamento=P.eh_credenciamento(lic["modalidade"]),
        fase=fase, efetivos=VINCULOS_EFETIVOS, funcoes=FUNCOES_EQUIPE,
        pode_suspender=bool(_ocorrencias_possiveis(lic)),
    )


@bp.route("/licitacoes/<int:id_>/editar", methods=["GET", "POST"])
@permissao("editar")
def editar(id_):
    lic = _buscar(id_)
    dados = dict(lic)
    pendentes = pontos = []
    if request.method == "POST":
        dados, erros, pendentes, pontos = _validar(request.form, lic)
        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            alteracoes = _descrever_alteracoes(lic, dados)
            novos_mantidos = (equipe.ler_mantidos(dados["impedimentos_mantidos"])
                              - equipe.ler_mantidos(lic["impedimentos_mantidos"]))
            if novos_mantidos:
                alteracoes.append("Mantido membro impedido (sessão em andamento)")
            if alteracoes:
                conn = get_db()
                conn.execute(
                    f"UPDATE licitacoes SET {', '.join(c + ' = ?' for c in CAMPOS)},"
                    " impedimentos_mantidos = ?,"
                    " atualizado_em = datetime('now', 'localtime') WHERE id = ?",
                    (*[dados[c] for c in CAMPOS], dados["impedimentos_mantidos"], id_),
                )
                if lic["status"] != dados["status"]:
                    # Suspensão e remarcação valem só para a fase em que foram registradas.
                    conn.execute("UPDATE licitacoes SET suspensa_em = NULL, ocorrencia = NULL,"
                                 " motivo_suspensao = NULL WHERE id = ?", (id_,))
                registrar("Alteração de licitação", referencia=identificacao(dados),
                          detalhes="; ".join(alteracoes), licitacao_id=id_)
                conn.commit()
                flash("Licitação atualizada.", "sucesso")
            else:
                flash("Nenhuma alteração foi feita.", "info")
            return redirect(url_for("agenda.detalhe", id_=id_))

    return _render_form(dados, f"Editar {identificacao(lic)}", lic, pendentes, pontos)


def _minuscula(texto):
    """Só a primeira letra em minúscula, preservando nomes próprios (ex.: Três Rios)."""
    return texto[:1].lower() + texto[1:]


def _formatar(valor):
    if not valor:
        return "—"
    if len(valor) == 10:
        return date.fromisoformat(valor).strftime("%d/%m/%Y")
    return datetime.fromisoformat(valor).strftime("%d/%m/%Y %H:%M")


def _descrever_alteracoes(antes, depois):
    nomes = {r["id"]: r["nome"] for r in get_db().execute("SELECT id, nome FROM servidores")}
    alteracoes = []
    for campo in CAMPOS:
        a, d = antes[campo], depois[campo]
        if a == d:
            continue
        if campo in EQUIPE:
            a, d = nomes.get(a, "—"), nomes.get(d, "—")
        elif campo == "status":
            a, d = P.situacao(a)["nome"], P.situacao(d)["nome"]
        elif campo == "prazo_hipotese":
            if a is None:
                continue
            a, d = PRAZOS.get(a, (a,))[0], PRAZOS.get(d, (d,))[0]
        elif campo in ("data_publicacao", "data_sessao", "vigencia_ate"):
            a, d = _formatar(a), _formatar(d)
        elif campo in ("objeto", "observacoes"):
            alteracoes.append(f"{ROTULOS[campo]} alterado")
            continue
        alteracoes.append(f"{ROTULOS[campo]}: {a if a is not None else '—'} → "
                          f"{d if d is not None else '—'}")
    return alteracoes


def _ocorrencias_possiveis(lic):
    """Suspensões e remarcações cabíveis conforme a sessão já tenha sido aberta ou não."""
    if P.eh_credenciamento(lic["modalidade"]) or lic["status"] == RECURSO:
        return {}
    fase = P.fase(lic["status"])
    if fase in FASES_ANTES_DA_SESSAO:
        momento = "antes"
    elif fase == "andamento":
        momento = "andamento"
    else:
        return {}
    return {k: v for k, v in OCORRENCIAS.items() if v["fase"] == momento}


@bp.route("/licitacoes/<int:id_>/suspender", methods=["GET", "POST"])
@permissao("suspender")
def suspender(id_):
    """Registra suspensão ou remarcação, antes da abertura ou com a sessão em andamento."""
    lic = _buscar(id_)
    opcoes = _ocorrencias_possiveis(lic)
    if not opcoes:
        abort(400, "Esta licitação não pode ser suspensa ou remarcada na situação atual.")

    agora = datetime.now().strftime("%Y-%m-%dT%H:%M")
    dados = {"tipo": next(iter(opcoes)), "suspensa_em": agora}
    pendentes = pontos = []
    if request.method == "POST":
        dados = {c: request.form.get(c, "").strip()
                 for c in ("tipo", "suspensa_em", "nova_data", "data_retificacao", "motivo",
                           "sem_novo_prazo")}
        erros = []
        tipo = opcoes.get(dados["tipo"])
        quando = None
        if tipo is None:
            erros.append("Escolha o que aconteceu com a sessão.")
        elif tipo["campo"] == "suspensa_em":
            try:
                quando = _ler_data(dados["suspensa_em"], com_hora=True)
            except ValueError:
                erros.append("Informe a data e a hora da suspensão.")
        else:
            try:
                quando = _ler_data(dados["nova_data"], com_hora=True)
                if quando <= agora:
                    erros.append("A nova data e hora da sessão deve ser futura.")
            except ValueError:
                erros.append("Informe a nova data e a hora da sessão.")
        retificacao = dados["tipo"] == "remarcada_retificacao"
        if retificacao and dados["data_retificacao"]:
            try:
                dados["data_retificacao"] = _ler_data(dados["data_retificacao"], com_hora=False)
            except ValueError:
                erros.append("Data da retificação inválida.")
                dados["data_retificacao"] = ""
        elif retificacao and not dados["sem_novo_prazo"]:
            erros.append("Informe a data de divulgação do edital retificado: o prazo mínimo "
                         "é contado de novo a partir dela (art. 55, § 1º).")

        # Nova data: dia útil e, antes da abertura, prazo mínimo legal (reaberto pela
        # retificação, salvo se ela não afetar a formulação das propostas).
        if tipo and tipo["campo"] == "nova_data" and quando and not erros:
            if tipo["fase"] == "antes":
                divulgacao = lic["retificado_em"] or lic["data_publicacao"]
                if retificacao and not dados["sem_novo_prazo"]:
                    divulgacao = dados["data_retificacao"]
                prazo = lic["prazo_hipotese"] or P.modalidade(lic["modalidade"])["prazo_padrao"]
            else:
                divulgacao, prazo = None, "nao_se_aplica"
            erros_data, pontos = criticar_sessao(
                quando, divulgacao, prazo, bool(request.form.get("confirmar_ponto_facultativo")))
            erros += erros_data

        mantidos = equipe.ler_mantidos(lic["impedimentos_mantidos"])
        if tipo and tipo["campo"] == "nova_data" and quando and not erros:
            erros_imp, pendentes, mantidos = equipe.verificar(
                [lic[c] for c in EQUIPE], quando, tipo["fase"] == "andamento", mantidos,
                manter=bool(request.form.get("manter_impedidos")),
            )
            if erros_imp and tipo["fase"] == "antes":
                erros_imp = [erros_imp[0].replace("Troque o membro da equipe.",
                             "Troque o membro pela edição da licitação antes de remarcar.")]
            erros += erros_imp

        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            conn = get_db()
            motivo = dados["motivo"] or None
            # Com a sessão aberta, a licitação continua na situação de andamento atual.
            if tipo["fase"] == "andamento":
                novo_status = lic["status"]
            else:
                novo_status = "suspensa" if tipo["campo"] == "suspensa_em" else "remarcada"
            if retificacao and not dados["sem_novo_prazo"]:
                conn.execute("UPDATE licitacoes SET retificado_em = ? WHERE id = ?",
                             (dados["data_retificacao"], id_))
            if tipo["campo"] == "suspensa_em":
                conn.execute(
                    "UPDATE licitacoes SET status = ?, ocorrencia = ?, suspensa_em = ?,"
                    " motivo_suspensao = ?, atualizado_em = datetime('now', 'localtime')"
                    " WHERE id = ?",
                    (novo_status, dados["tipo"], quando, motivo, id_),
                )
                detalhes = f"Suspensa em {_formatar(quando)}"
            else:
                conn.execute(
                    "UPDATE licitacoes SET status = ?, ocorrencia = ?, data_sessao = ?,"
                    " suspensa_em = NULL, motivo_suspensao = NULL, impedimentos_mantidos = ?,"
                    " atualizado_em = datetime('now', 'localtime') WHERE id = ?",
                    (novo_status, dados["tipo"], quando,
                     ",".join(map(str, sorted(mantidos))) or None, id_),
                )
                detalhes = f"De {_formatar(lic['data_sessao'])} para {_formatar(quando)}"
                if retificacao and dados["data_retificacao"]:
                    detalhes += f". Edital retificado em {_formatar(dados['data_retificacao'])}"
                if retificacao and dados["sem_novo_prazo"]:
                    detalhes += (". Sem reabertura de prazo: a alteração não compromete a "
                                 "formulação das propostas (art. 55, § 1º)")
            if mantidos - equipe.ler_mantidos(lic["impedimentos_mantidos"]):
                detalhes += ". Mantido membro impedido"
            if motivo:
                detalhes += f". Motivo: {motivo}"
            registrar(tipo["rotulo"], referencia=identificacao(lic), detalhes=detalhes,
                      licitacao_id=id_)
            conn.commit()
            flash(f"{tipo['rotulo']}: registrado.", "sucesso")
            return redirect(url_for("agenda.detalhe", id_=id_))

    return render_template("agenda/suspender.html", lic=lic, dados=dados, opcoes=opcoes,
                           pendentes=pendentes, pontos=pontos, fase=P.fase(lic["status"]))


def _pode_recorrer(lic):
    return (P.fase(lic["status"]) == "andamento" and lic["status"] != RECURSO
            and not P.eh_credenciamento(lic["modalidade"]) and not lic["recurso_id"])


CAMPOS_RECURSO = {
    "intimado_em": "Intimação / ata",
    "notificado_em": "Notificação das empresas sobre o recurso",
    "razoes_ate": "Razões até",
    "contrarrazoes_ate": "Contrarrazões até",
    "reconsideracao_ate": "Reconsideração até",
    "decisao_ate": "Decisão até",
}
OBRIGATORIOS_RECURSO = ["intimado_em", "razoes_ate", "contrarrazoes_ate",
                        "reconsideracao_ate", "decisao_ate"]


def _validar_recurso(form):
    """Datas informadas pelo pregoeiro: em ordem e com vencimentos em dias úteis."""
    dados = {c: form.get(c, "").strip() for c in (*CAMPOS_RECURSO, "observacao")}
    erros = []
    for campo, rotulo in CAMPOS_RECURSO.items():
        if not dados[campo]:
            if campo in OBRIGATORIOS_RECURSO:
                erros.append(f"Informe: {rotulo}.")
            dados[campo] = None
            continue
        try:
            dados[campo] = date.fromisoformat(dados[campo]).isoformat()
        except ValueError:
            erros.append(f"{rotulo}: data inválida.")
            dados[campo] = None
    if not erros:
        sequencia = [c for c in OBRIGATORIOS_RECURSO if dados[c]]
        for anterior, seguinte in zip(sequencia, sequencia[1:]):
            if dados[seguinte] < dados[anterior]:
                erros.append(f"{CAMPOS_RECURSO[seguinte]} não pode ser antes de "
                             f"{CAMPOS_RECURSO[anterior].lower()}.")
        if dados["notificado_em"] and dados["notificado_em"] < dados["intimado_em"]:
            erros.append("A notificação das empresas não pode ser antes da intimação/ata.")
        # Prazo que vence em dia sem expediente se prorroga (art. 183, § 2º).
        for campo in ("razoes_ate", "contrarrazoes_ate", "reconsideracao_ate", "decisao_ate"):
            motivos = feriados.motivos(date.fromisoformat(dados[campo]))
            if motivos:
                erros.append(f"{CAMPOS_RECURSO[campo]}: {_formatar(dados[campo])} não é dia "
                             f"útil ({_minuscula(feriados.descrever(motivos[0]))}).")
    return dados, erros


def _descrever_prazos_recurso(dados):
    return "; ".join(f"{rotulo}: {_formatar(dados[c])}" for c, rotulo in CAMPOS_RECURSO.items()
                     if dados.get(c))


def _render_recurso(lic, dados, editando):
    return render_template(
        "agenda/recurso.html", lic=lic, dados=dados, editando=editando,
        prazos_legais=(PRAZO_RAZOES, PRAZO_CONTRARRAZOES, PRAZO_RECONSIDERACAO, PRAZO_DECISAO),
        nao_uteis=feriados.dias_nao_uteis(date.today() - timedelta(days=120),
                                          date.today() + timedelta(days=240)),
    )


@bp.route("/licitacoes/<int:id_>/recurso", methods=["GET", "POST"])
@permissao("recursos")
def recurso(id_):
    """Recurso (art. 165). O pregoeiro informa as datas; o sistema sugere os prazos legais
    em dias úteis a partir da intimação/ata (e da notificação das empresas, se houver)."""
    lic = _buscar(id_)
    if not _pode_recorrer(lic):
        abort(400, "Só cabe registrar recurso com a sessão em andamento e sem outro recurso "
                   "pendente.")
    dados = {"intimado_em": date.today().isoformat(), **prazos_recurso(date.today())}
    if request.method == "POST":
        dados, erros = _validar_recurso(request.form)
        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            conn = get_db()
            conn.execute(
                "INSERT INTO recursos (licitacao_id, intimado_em, notificado_em, razoes_ate,"
                " contrarrazoes_ate, reconsideracao_ate, decisao_ate, status_anterior,"
                " observacao) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (id_, dados["intimado_em"], dados["notificado_em"], dados["razoes_ate"],
                 dados["contrarrazoes_ate"], dados["reconsideracao_ate"], dados["decisao_ate"],
                 lic["status"], dados["observacao"] or None),
            )
            conn.execute("UPDATE licitacoes SET status = ?, suspensa_em = NULL,"
                         " motivo_suspensao = NULL, ocorrencia = NULL,"
                         " atualizado_em = datetime('now', 'localtime') WHERE id = ?",
                         (RECURSO, id_))
            registrar("Recurso interposto", referencia=identificacao(lic), licitacao_id=id_,
                      detalhes=_descrever_prazos_recurso(dados))
            conn.commit()
            flash("Recurso registrado.", "sucesso")
            return redirect(url_for("agenda.detalhe", id_=id_))
    return _render_recurso(lic, dados, editando=False)


@bp.route("/licitacoes/<int:id_>/recurso/prazos", methods=["GET", "POST"])
@permissao("recursos")
def editar_recurso(id_):
    """Ajuste dos prazos durante o recurso (ex.: notificação das empresas na licitação
    presencial, que reabre a contagem das contrarrazões)."""
    lic = _buscar(id_)
    if not lic["recurso_id"]:
        abort(400, "Não há recurso pendente nesta licitação.")
    conn = get_db()
    atual = conn.execute("SELECT * FROM recursos WHERE id = ?", (lic["recurso_id"],)).fetchone()
    dados = dict(atual)
    if request.method == "POST":
        dados, erros = _validar_recurso(request.form)
        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            mudancas = [f"{rotulo}: {_formatar(atual[c])} → {_formatar(dados[c])}"
                        for c, rotulo in CAMPOS_RECURSO.items() if atual[c] != dados[c]]
            conn.execute(
                "UPDATE recursos SET intimado_em = ?, notificado_em = ?, razoes_ate = ?,"
                " contrarrazoes_ate = ?, reconsideracao_ate = ?, decisao_ate = ?,"
                " observacao = ? WHERE id = ?",
                (dados["intimado_em"], dados["notificado_em"], dados["razoes_ate"],
                 dados["contrarrazoes_ate"], dados["reconsideracao_ate"], dados["decisao_ate"],
                 dados["observacao"] or None, atual["id"]),
            )
            if mudancas:
                registrar("Prazos do recurso alterados", referencia=identificacao(lic),
                          licitacao_id=id_, detalhes="; ".join(mudancas))
            conn.commit()
            flash("Prazos do recurso atualizados." if mudancas else "Nenhuma alteração.",
                  "sucesso" if mudancas else "info")
            return redirect(url_for("agenda.detalhe", id_=id_))
    return _render_recurso(lic, dados, editando=True)


@bp.route("/licitacoes/<int:id_>/recurso/decisao", methods=["GET", "POST"])
@permissao("recursos")
def decidir_recurso(id_):
    lic = _buscar(id_)
    if not lic["recurso_id"]:
        abort(400, "Não há recurso pendente nesta licitação.")
    anterior = get_db().execute("SELECT status_anterior FROM recursos WHERE id = ?",
                                (lic["recurso_id"],)).fetchone()[0]
    destinos = [s for s in P.situacoes(True) if s["fase"] in ("andamento", "concluida",
                                                              "encerrada")
                and s["chave"] != RECURSO]
    dados = {"decidido_em": date.today().isoformat(),
             "status": anterior if anterior and anterior != RECURSO else "andamento"}
    if request.method == "POST":
        dados = {c: request.form.get(c, "").strip()
                 for c in ("decidido_em", "resultado", "status", "observacao")}
        erros = []
        try:
            decidido = date.fromisoformat(dados["decidido_em"])
        except ValueError:
            erros.append("Informe a data da decisão.")
        if dados["resultado"] not in RESULTADOS_RECURSO:
            erros.append("Informe o resultado do recurso.")
        if dados["status"] not in {s["chave"] for s in destinos}:
            erros.append("Escolha a situação da licitação após a decisão.")
        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            conn = get_db()
            conn.execute("UPDATE recursos SET decidido_em = ?, resultado = ?,"
                         " observacao = COALESCE(?, observacao) WHERE id = ?",
                         (decidido.isoformat(), dados["resultado"], dados["observacao"] or None,
                          lic["recurso_id"]))
            conn.execute("UPDATE licitacoes SET status = ?,"
                         " atualizado_em = datetime('now', 'localtime') WHERE id = ?",
                         (dados["status"], id_))
            registrar("Decisão do recurso", referencia=identificacao(lic), licitacao_id=id_,
                      detalhes=f"{dados['resultado']} em {_formatar(decidido.isoformat())}. "
                               f"Situação: {P.situacao(dados['status'])['nome']}")
            conn.commit()
            flash("Decisão do recurso registrada.", "sucesso")
            return redirect(url_for("agenda.detalhe", id_=id_))
    return render_template("agenda/decisao_recurso.html", lic=lic, dados=dados,
                           destinos=destinos, resultados=RESULTADOS_RECURSO)


@bp.route("/licitacoes/<int:id_>/renovar", methods=["POST"])
@permissao("editar")
def renovar(id_):
    """Renova por mais um ano a vigência de um credenciamento em andamento."""
    lic = _buscar(id_)
    if not P.eh_credenciamento(lic["modalidade"]) or P.fase(lic["status"]) != "andamento":
        abort(400, "Só credenciamentos em andamento podem ser renovados.")
    base = date.fromisoformat(lic["vigencia_ate"]) if lic["vigencia_ate"] else date.today()
    nova = somar_um_ano(base).isoformat()
    conn = get_db()
    conn.execute("UPDATE licitacoes SET vigencia_ate = ?,"
                 " atualizado_em = datetime('now', 'localtime') WHERE id = ?", (nova, id_))
    registrar("Renovação do credenciamento", referencia=identificacao(lic),
              detalhes=f"Vigência: {_formatar(lic['vigencia_ate'])} → {_formatar(nova)}",
              licitacao_id=id_)
    conn.commit()
    flash(f"Credenciamento renovado até {_formatar(nova)}.", "sucesso")
    return redirect(url_for("agenda.detalhe", id_=id_))


@bp.route("/licitacoes/<int:id_>/excluir", methods=["POST"])
@permissao("excluir")
def excluir(id_):
    lic = _buscar(id_)
    conn = get_db()
    conn.execute("DELETE FROM licitacoes WHERE id = ?", (id_,))
    registrar("Exclusão de licitação", referencia=identificacao(lic),
              detalhes=f"{lic['modalidade']} — {lic['objeto'][:200]}")
    conn.commit()
    flash(f"Licitação {identificacao(lic)} excluída.", "sucesso")
    return redirect(url_for("agenda.lista"))


# --- WhatsApp e exportação ---------------------------------------------------------------

def _abertas():
    """Licitações abertas ou em andamento: sessões agendadas, depois as suspensas antes da
    abertura e, por fim, os credenciamentos."""
    chaves = [s["chave"] for s in P.situacoes() if s["whatsapp"]] or [""]
    linhas = get_db().execute(
        CONSULTA_BASE + f" WHERE l.status IN ({_em(chaves)})", chaves).fetchall()
    return sorted(linhas, key=lambda l: (
        P.eh_credenciamento(l["modalidade"]),
        P.fase(l["status"]) == "suspensa" or bool(l["suspensa_em"]),
        l["data_sessao"] or l["vigencia_ate"] or "",
    ))


def _texto_whatsapp(licitacoes):
    """Mesmo conteúdo da imagem, como texto (*negrito*), para colar se preferir."""
    linhas = [f"*Licitações abertas — {P.nome_orgao()}*",
              f"_Atualizado em {datetime.now():%d/%m/%Y às %H:%M}_"]
    for lic in licitacoes:
        bloco = imagem.conteudo(lic)
        linhas.append("")
        linhas.append(f"*{bloco['titulo']}* — {lic['modalidade']}")
        linhas.append(bloco["quando"])
        linhas.append(f"Objeto: {lic['objeto']}")
        linhas += bloco["equipe"]
    if not licitacoes:
        linhas.append("\nNão há licitações abertas no momento.")
    return "\n".join(linhas)


def _paginas(licitacoes):
    return imagem.paginar([imagem.conteudo(l) for l in licitacoes], "Licitações abertas",
                          P.nome_orgao())


@bp.route("/licitacoes/whatsapp")
@permissao("ver")
def whatsapp():
    """Imagens no formato de tela de celular com as licitações abertas ou em andamento."""
    licitacoes = _abertas()
    total = len(_paginas(licitacoes)[0])
    imagens = [url_for("agenda.whatsapp_imagem", pagina=n, v=datetime.now().strftime("%H%M%S"))
               for n in range(1, total + 1)]
    return render_template("agenda/whatsapp.html", imagens=imagens, total=len(licitacoes),
                           texto=_texto_whatsapp(licitacoes), titulo="Licitações abertas",
                           nome_arquivo="licitacoes-abertas")


@bp.route("/licitacoes/whatsapp/<int:pagina>.png")
@permissao("ver")
def whatsapp_imagem(pagina):
    paginas, layout = _paginas(_abertas())
    if not 1 <= pagina <= len(paginas):
        abort(404)
    png = imagem.desenhar(paginas[pagina - 1], pagina, len(paginas), "Licitações abertas",
                          P.nome_orgao(), layout)
    return Response(png, mimetype="image/png", headers={"Cache-Control": "no-store"})


@bp.route("/licitacoes/<int:id_>/whatsapp")
@permissao("ver")
def whatsapp_licitacao(id_):
    lic = _buscar(id_)
    return render_template(
        "agenda/whatsapp.html", total=1, texto=_texto_whatsapp([lic]),
        imagens=[url_for("agenda.whatsapp_licitacao_imagem", id_=id_,
                         v=datetime.now().strftime("%H%M%S"))],
        titulo=identificacao(lic), nome_arquivo=f"licitacao-{id_}", lic=lic,
    )


@bp.route("/licitacoes/<int:id_>/whatsapp.png")
@permissao("ver")
def whatsapp_licitacao_imagem(id_):
    lic = _buscar(id_)
    png = imagem.desenhar([imagem.conteudo(lic)], 1, 1, "Licitação", P.nome_orgao())
    return Response(png, mimetype="image/png", headers={"Cache-Control": "no-store"})


@bp.route("/licitacoes.ics")
@permissao("ver")
def exportar_ics():
    """Exporta as licitações filtradas para Outlook, Google Agenda etc."""
    where, params = _filtrar(request.args)
    licitacoes = get_db().execute(
        CONSULTA_BASE + where + " ORDER BY l.data_sessao", params
    ).fetchall()

    def esc(texto):
        return (texto or "").replace("\\", "\\\\").replace(";", "\\;") \
            .replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")

    carimbo = datetime.now().strftime("%Y%m%dT%H%M%S")
    linhas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Agenda de Licitacoes//PT-BR",
              "CALSCALE:GREGORIAN"]
    for lic in licitacoes:
        fase = P.fase(lic["status"])
        descricao = f"Processo {lic['numero_processo']} — {lic['objeto']}"
        descricao += "\n" + "\n".join(imagem.conteudo(lic)["equipe"])
        if P.eh_credenciamento(lic["modalidade"]):
            if not lic["vigencia_ate"] or fase != "andamento":
                continue
            inicio = [f"DTSTART;VALUE=DATE:{lic['vigencia_ate'].replace('-', '')}"]
            resumo = f"Renovar credenciamento {identificacao(lic)}"
        elif lic["data_sessao"]:
            dt = datetime.fromisoformat(lic["data_sessao"])
            inicio = [f"DTSTART:{dt.strftime('%Y%m%dT%H%M%S')}", "DURATION:PT2H"]
            resumo = f"{identificacao(lic)} — {lic['modalidade']}"
            if fase == "suspensa" or lic["suspensa_em"]:
                resumo = f"[SUSPENSA] {resumo}"
        else:
            continue
        linhas += [
            "BEGIN:VEVENT",
            f"UID:licitacao-{lic['id']}@agenda-licitacoes",
            f"DTSTAMP:{carimbo}",
            *inicio,
            f"SUMMARY:{esc(resumo)}",
            f"DESCRIPTION:{esc(descricao)}",
            f"LOCATION:{esc(lic['local'])}",
            f"STATUS:{'CANCELLED' if fase == 'encerrada' else 'CONFIRMED'}",
            "END:VEVENT",
        ]
    linhas.append("END:VCALENDAR")
    return Response(
        "\r\n".join(linhas) + "\r\n",
        mimetype="text/calendar",
        headers={"Content-Disposition": "attachment; filename=licitacoes.ics"},
    )
