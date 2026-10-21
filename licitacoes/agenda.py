"""Agenda, calendário e cadastro de licitações."""
import calendar
from datetime import date, datetime, timedelta

from flask import (
    Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request,
    url_for,
)

from . import equipe, imagem
from .auth import permissao
from .db import get_db, registrar
from .perfis import (
    CORES_MODALIDADE, CREDENCIAMENTO, EQUIPE_OBRIGATORIA, FUNCOES_EQUIPE, MODALIDADES,
    OCORRENCIAS, STATUS, STATUS_ABERTOS, STATUS_CREDENCIAMENTO, STATUS_DIVULGAVEIS,
    VINCULOS_EFETIVOS,
)

bp = Blueprint("agenda", __name__)

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

EQUIPE = equipe.EQUIPE

CAMPOS = ["numero_processo", "numero_edital", "modalidade", "objeto", "data_publicacao",
          "data_sessao", "vigencia_ate", "local", *EQUIPE, "valor_estimado", "status",
          "observacoes"]

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
    "observacoes": "Observações",
}

# Situações só alcançadas pela ação "Suspender / remarcar".
STATUS_DA_ACAO_SUSPENDER = {"Suspensa", "Remarcada"}

# Situações em que a sessão ainda não foi aberta, mas o edital já saiu.
STATUS_ANTES_DA_SESSAO = ["Edital publicado", "Remarcada", "Suspensa"]

# Modalidades sem sessão pública conduzida por pregoeiro / agente.
SEM_EQUIPE_OBRIGATORIA = {"Inexigibilidade"}

CONSULTA_BASE = """
    SELECT l.*,
           a.nome AS agente_nome, m1.nome AS membro1_nome, m2.nome AS membro2_nome,
           m3.nome AS membro3_nome
      FROM licitacoes l
      LEFT JOIN servidores a  ON a.id  = l.agente_id
      LEFT JOIN servidores m1 ON m1.id = l.membro1_id
      LEFT JOIN servidores m2 ON m2.id = l.membro2_id
      LEFT JOIN servidores m3 ON m3.id = l.membro3_id
"""


def situacao(lic):
    """Situação por extenso, distinguindo as fases de suspensão e remarcação."""
    status, ocorrencia = lic["status"], lic["ocorrencia"]
    if status == "Suspensa":
        return "Suspensa — sessão não aberta"
    if status == "Remarcada" and ocorrencia == "remarcada_retificacao":
        return "Remarcada — edital retificado"
    if status == "Em andamento" and lic["suspensa_em"]:
        return "Em andamento — suspensa p/ análise documental"
    if status == "Em andamento" and ocorrencia == "continuacao":
        return "Em andamento — continuação"
    return status


def identificacao(lic):
    return lic["numero_edital"] or f"Processo {lic['numero_processo']}"


def _buscar(id_):
    lic = get_db().execute(CONSULTA_BASE + " WHERE l.id = ?", (id_,)).fetchone()
    if lic is None:
        abort(404)
    return lic


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


def _validar(form, atual=None):
    """Retorna (dados, erros, impedidos pendentes de decisão)."""
    dados = {c: form.get(c, "").strip() for c in CAMPOS}
    erros = []

    for campo in ("numero_processo", "objeto"):
        if not dados[campo]:
            erros.append(f"Informe o campo “{ROTULOS[campo]}”.")
    if dados["modalidade"] not in MODALIDADES:
        erros.append("Selecione uma modalidade válida.")
    credenciamento = dados["modalidade"] == CREDENCIAMENTO

    if dados["status"] not in STATUS:
        erros.append("Selecione uma situação válida.")
    elif credenciamento and dados["status"] not in STATUS_CREDENCIAMENTO:
        erros.append("Credenciamento só pode estar “Em andamento” ou “Concluída”.")
    elif dados["status"] in STATUS_DA_ACAO_SUSPENDER and (
        atual is None or atual["status"] != dados["status"]
    ):
        erros.append("Para suspender ou remarcar a sessão, use o botão “Suspender / remarcar”.")
    if not dados["numero_edital"] and dados["status"] != "Em planejamento":
        erros.append("Informe o número do edital (ex.: PE 007/2026).")

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
        if not dados["data_sessao"] and dados["status"] != "Em planejamento":
            erros.append("Informe a data e a hora da sessão.")
        if (dados["data_sessao"] and dados["data_publicacao"]
                and dados["data_sessao"][:10] < dados["data_publicacao"]):
            erros.append("A sessão não pode ser anterior à publicação do edital.")

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
    exige_equipe = (dados["status"] != "Em planejamento"
                    and dados["modalidade"] not in SEM_EQUIPE_OBRIGATORIA)
    if exige_equipe and not all(dados[c] for c in EQUIPE_OBRIGATORIA):
        erros.append("Informe a equipe: pregoeiro / agente de contratação e dois membros.")
    erros += equipe.problemas(ids, servidores)

    mantidos = equipe.ler_mantidos(atual["impedimentos_mantidos"] if atual else "")
    erros_imp, pendentes, mantidos = equipe.verificar(
        ids, dados["data_sessao"], dados["status"] == "Em andamento", mantidos,
        manter=bool(form.get("manter_impedidos")),
    )
    erros += erros_imp
    dados["impedimentos_mantidos"] = ",".join(map(str, sorted(mantidos))) or None

    for campo in ("numero_edital", "local", "observacoes"):
        dados[campo] = dados[campo] or None

    return dados, erros, pendentes


def _filtrar(args):
    """Monta a cláusula WHERE a partir dos filtros da listagem."""
    condicoes, params = [], []
    termo = args.get("q", "").strip()
    if termo:
        condicoes.append("(l.objeto LIKE ? OR l.numero_processo LIKE ? OR l.numero_edital LIKE ?)")
        params += [f"%{termo}%"] * 3
    if args.get("modalidade") in MODALIDADES:
        condicoes.append("l.modalidade = ?")
        params.append(args["modalidade"])
    if args.get("status") in STATUS:
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


def _em(lista):
    return ",".join("?" * len(lista))


def _impedimentos_abertos():
    """Integrantes afastados na data de sessões futuras ainda não decididas."""
    conn = get_db()
    linhas = conn.execute(
        CONSULTA_BASE.replace("SELECT l.*,", "SELECT l.*, af.id AS afastamento_id,"
                              " af.tipo, af.inicio, af.fim, sv.nome,")
        + " JOIN afastamentos af ON af.servidor_id IN"
          "      (l.agente_id, l.membro1_id, l.membro2_id, l.membro3_id)"
          "  AND substr(l.data_sessao, 1, 10) BETWEEN af.inicio AND af.fim"
          " JOIN servidores sv ON sv.id = af.servidor_id"
        f" WHERE l.status IN ({_em(STATUS_ABERTOS)}) AND l.status != 'Suspensa'"
          "   AND substr(l.data_sessao, 1, 10) >= ?"
          " ORDER BY l.data_sessao",
        (*STATUS_ABERTOS, date.today().isoformat()),
    ).fetchall()
    return [l for l in linhas
            if l["afastamento_id"] not in equipe.ler_mantidos(l["impedimentos_mantidos"])]


@bp.app_template_global()
def cor_modalidade(modalidade):
    return CORES_MODALIDADE.get(modalidade, ("#ffffff", "#4b5563"))


@bp.app_context_processor
def _globais():
    return {"situacao": situacao, "OCORRENCIAS": OCORRENCIAS}


@bp.route("/")
@permissao("ver")
def painel():
    conn = get_db()
    agora = datetime.now().strftime("%Y-%m-%dT%H:%M")
    hoje = date.today()
    com_sessao = [s for s in STATUS_ABERTOS if s != "Suspensa"]

    # Sem limite de prazo: há editais publicados com bem mais de 30 dias de antecedência.
    proximas = conn.execute(
        CONSULTA_BASE + f" WHERE l.data_sessao >= ? AND l.status IN ({_em(com_sessao)})"
        " AND l.suspensa_em IS NULL ORDER BY l.data_sessao",
        (agora, *com_sessao),
    ).fetchall()
    sessoes_hoje = [l for l in proximas if l["data_sessao"].startswith(hoje.isoformat())]
    suspensas = conn.execute(
        CONSULTA_BASE + " WHERE l.status = 'Suspensa'"
        " OR (l.status = 'Em andamento' AND l.suspensa_em IS NOT NULL)"
        " ORDER BY l.status = 'Suspensa', l.suspensa_em"
    ).fetchall()
    credenciamentos = conn.execute(
        CONSULTA_BASE + " WHERE l.modalidade = ? AND l.status = 'Em andamento'"
        " ORDER BY l.vigencia_ate",
        (CREDENCIAMENTO,),
    ).fetchall()
    atrasadas = conn.execute(
        CONSULTA_BASE + f" WHERE l.data_sessao < ? AND l.status IN ({_em(com_sessao)})"
        " AND l.suspensa_em IS NULL ORDER BY l.data_sessao",
        (agora, *com_sessao),
    ).fetchall()
    contagem = dict(conn.execute(
        "SELECT status, COUNT(*) FROM licitacoes GROUP BY status"
    ).fetchall())
    modalidades_em_uso = sorted({l["modalidade"] for l in (*proximas, *suspensas, *atrasadas)},
                                key=MODALIDADES.index)

    return render_template(
        "agenda/painel.html", proximas=proximas, sessoes_hoje=sessoes_hoje,
        suspensas=suspensas, credenciamentos=credenciamentos, atrasadas=atrasadas,
        impedidos=_impedimentos_abertos(), contagem=contagem, hoje=hoje.isoformat(),
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
    eventos = {}
    for lic in get_db().execute(
        CONSULTA_BASE + " WHERE (l.data_sessao >= ? AND l.data_sessao < ?)"
        " OR (l.modalidade = ? AND l.status = 'Em andamento'"
        "     AND l.vigencia_ate >= ? AND l.vigencia_ate < ?)"
        " ORDER BY l.data_sessao",
        (inicio, fim, CREDENCIAMENTO, inicio, fim),
    ):
        if lic["modalidade"] == CREDENCIAMENTO:
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
        hoje=hoje, anterior=anterior, seguinte=seguinte, modalidades=MODALIDADES,
    )


@bp.route("/licitacoes")
@permissao("ver")
def lista():
    where, params = _filtrar(request.args)
    licitacoes = get_db().execute(
        CONSULTA_BASE + where + " ORDER BY COALESCE(l.data_sessao, l.data_publicacao) DESC",
        params,
    ).fetchall()
    return render_template(
        "agenda/lista.html", licitacoes=licitacoes, modalidades=MODALIDADES,
        servidores=equipe.servidores(), filtros=request.args,
    )


def _render_form(dados, titulo, atual=None, pendentes=()):
    return render_template(
        "agenda/form.html", dados=dados, titulo=titulo, atual=atual, pendentes=pendentes,
        modalidades=MODALIDADES, servidores=equipe.servidores([dados.get(c) for c in EQUIPE]),
        status_form=[s for s in STATUS if s not in STATUS_DA_ACAO_SUSPENDER
                     or (atual and atual["status"] == s)],
        status_credenciamento=STATUS_CREDENCIAMENTO, credenciamento=CREDENCIAMENTO,
        efetivos=VINCULOS_EFETIVOS, funcoes=FUNCOES_EQUIPE,
    )


@bp.route("/licitacoes/nova", methods=["GET", "POST"])
@permissao("criar")
def nova():
    dados = {"status": "Em planejamento"}
    pendentes = []
    if request.method == "POST":
        dados, erros, pendentes = _validar(request.form)
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

    return _render_form(dados, "Nova licitação", pendentes=pendentes)


@bp.route("/licitacoes/<int:id_>")
@permissao("ver")
def detalhe(id_):
    lic = _buscar(id_)
    conn = get_db()
    historico = conn.execute(
        "SELECT h.*, u.nome AS usuario_nome FROM historico h"
        " LEFT JOIN usuarios u ON u.id = h.usuario_id"
        " WHERE h.licitacao_id = ? ORDER BY h.id DESC",
        (id_,),
    ).fetchall()
    ids = [lic[c] for c in EQUIPE]
    escalados = {s["id"]: s for s in equipe.servidores(ids)}
    # A escala pode ter ficado irregular depois (mudança de vínculo, férias lançadas...).
    alertas = equipe.problemas([i for i in ids if i], list(escalados.values()))
    if lic["status"] in STATUS_ABERTOS and lic["status"] != "Suspensa":
        alertas += equipe.verificar(
            ids, lic["data_sessao"], lic["status"] == "Em andamento",
            equipe.ler_mantidos(lic["impedimentos_mantidos"]), manter=False)[0]
    return render_template(
        "agenda/detalhe.html", lic=lic, historico=historico, escalados=escalados,
        alertas_equipe=alertas, credenciamento=CREDENCIAMENTO, efetivos=VINCULOS_EFETIVOS,
        funcoes=FUNCOES_EQUIPE, pode_suspender=bool(_ocorrencias_possiveis(lic)),
    )


@bp.route("/licitacoes/<int:id_>/editar", methods=["GET", "POST"])
@permissao("editar")
def editar(id_):
    lic = _buscar(id_)
    dados = dict(lic)
    pendentes = []
    if request.method == "POST":
        dados, erros, pendentes = _validar(request.form, lic)
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

    return _render_form(dados, f"Editar {identificacao(lic)}", lic, pendentes)


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
    if lic["modalidade"] == CREDENCIAMENTO:
        return {}
    if lic["status"] in STATUS_ANTES_DA_SESSAO:
        fase = "antes"
    elif lic["status"] == "Em andamento":
        fase = "andamento"
    else:
        return {}
    return {k: v for k, v in OCORRENCIAS.items() if v["fase"] == fase}


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
    pendentes = []
    if request.method == "POST":
        dados = {c: request.form.get(c, "").strip()
                 for c in ("tipo", "suspensa_em", "nova_data", "data_retificacao", "motivo")}
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
        if dados["tipo"] == "remarcada_retificacao" and dados["data_retificacao"]:
            try:
                dados["data_retificacao"] = _ler_data(dados["data_retificacao"], com_hora=False)
            except ValueError:
                erros.append("Data da retificação inválida.")

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
            if tipo["campo"] == "suspensa_em":
                novo_status = "Suspensa" if tipo["fase"] == "antes" else "Em andamento"
                conn.execute(
                    "UPDATE licitacoes SET status = ?, ocorrencia = ?, suspensa_em = ?,"
                    " motivo_suspensao = ?, atualizado_em = datetime('now', 'localtime')"
                    " WHERE id = ?",
                    (novo_status, dados["tipo"], quando, motivo, id_),
                )
                detalhes = f"Suspensa em {_formatar(quando)}"
            else:
                novo_status = "Remarcada" if tipo["fase"] == "antes" else "Em andamento"
                conn.execute(
                    "UPDATE licitacoes SET status = ?, ocorrencia = ?, data_sessao = ?,"
                    " suspensa_em = NULL, motivo_suspensao = NULL, impedimentos_mantidos = ?,"
                    " atualizado_em = datetime('now', 'localtime') WHERE id = ?",
                    (novo_status, dados["tipo"], quando,
                     ",".join(map(str, sorted(mantidos))) or None, id_),
                )
                detalhes = f"De {_formatar(lic['data_sessao'])} para {_formatar(quando)}"
                if dados["tipo"] == "remarcada_retificacao" and dados["data_retificacao"]:
                    detalhes += f". Edital retificado em {_formatar(dados['data_retificacao'])}"
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
                           pendentes=pendentes)


@bp.route("/licitacoes/<int:id_>/renovar", methods=["POST"])
@permissao("editar")
def renovar(id_):
    """Renova por mais um ano a vigência de um credenciamento em andamento."""
    lic = _buscar(id_)
    if lic["modalidade"] != CREDENCIAMENTO or lic["status"] != "Em andamento":
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


def _abertas():
    """Licitações abertas ou em andamento, para divulgação."""
    return get_db().execute(
        CONSULTA_BASE + f" WHERE l.status IN ({_em(STATUS_DIVULGAVEIS)})"
        # Primeiro as sessões agendadas, depois as suspensas e, por fim, os credenciamentos.
        " ORDER BY l.modalidade = ?, (l.status = 'Suspensa' OR l.suspensa_em IS NOT NULL),"
        " COALESCE(l.data_sessao, l.vigencia_ate)",
        (*STATUS_DIVULGAVEIS, CREDENCIAMENTO),
    ).fetchall()


def _texto_whatsapp(licitacoes):
    """Mesmo conteúdo da imagem, como texto (*negrito*), para colar se preferir."""
    linhas = [f"*Licitações abertas — {current_app.config['NOME_ORGAO']}*",
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
    return imagem.paginar([imagem.conteudo(l) for l in licitacoes])


@bp.route("/licitacoes/whatsapp")
@permissao("ver")
def whatsapp():
    """Imagens no formato de tela de celular com as licitações abertas ou em andamento."""
    licitacoes = _abertas()
    total = len(_paginas(licitacoes))
    imagens = [url_for("agenda.whatsapp_imagem", pagina=n, v=datetime.now().strftime("%H%M%S"))
               for n in range(1, total + 1)]
    return render_template("agenda/whatsapp.html", imagens=imagens, total=len(licitacoes),
                           texto=_texto_whatsapp(licitacoes), titulo="Licitações abertas",
                           nome_arquivo="licitacoes-abertas")


@bp.route("/licitacoes/whatsapp/<int:pagina>.png")
@permissao("ver")
def whatsapp_imagem(pagina):
    paginas = _paginas(_abertas())
    if not 1 <= pagina <= len(paginas):
        abort(404)
    png = imagem.desenhar(paginas[pagina - 1], pagina, len(paginas),
                          "Licitações abertas", current_app.config["NOME_ORGAO"])
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
    png = imagem.desenhar([imagem.conteudo(lic)], 1, 1, "Licitação",
                          current_app.config["NOME_ORGAO"])
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
        descricao = f"Processo {lic['numero_processo']} — {lic['objeto']}"
        descricao += "\n" + "\n".join(imagem.conteudo(lic)["equipe"])
        if lic["modalidade"] == CREDENCIAMENTO:
            if not lic["vigencia_ate"] or lic["status"] != "Em andamento":
                continue
            inicio = [f"DTSTART;VALUE=DATE:{lic['vigencia_ate'].replace('-', '')}"]
            resumo = f"Renovar credenciamento {identificacao(lic)}"
        elif lic["data_sessao"]:
            dt = datetime.fromisoformat(lic["data_sessao"])
            inicio = [f"DTSTART:{dt.strftime('%Y%m%dT%H%M%S')}", "DURATION:PT2H"]
            resumo = f"{identificacao(lic)} — {lic['modalidade']}"
            if lic["status"] == "Suspensa" or lic["suspensa_em"]:
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
            f"STATUS:{'CANCELLED' if STATUS[lic['status']] == 'vermelho' else 'CONFIRMED'}",
            "END:VEVENT",
        ]
    linhas.append("END:VCALENDAR")
    return Response(
        "\r\n".join(linhas) + "\r\n",
        mimetype="text/calendar",
        headers={"Content-Disposition": "attachment; filename=licitacoes.ics"},
    )
