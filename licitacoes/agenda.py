"""Agenda, calendário e cadastro de licitações."""
import calendar
from datetime import date, datetime, timedelta
from urllib.parse import quote

from flask import (
    Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request,
    url_for,
)

from .auth import permissao
from .db import get_db, registrar
from .perfis import (
    CREDENCIAMENTO, FUNCOES_EQUIPE, MODALIDADES, STATUS, STATUS_ABERTOS,
    STATUS_CREDENCIAMENTO, STATUS_DIVULGAVEIS, VINCULOS_EFETIVOS,
)

bp = Blueprint("agenda", __name__)

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

EQUIPE = list(FUNCOES_EQUIPE)

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

# Modalidades sem sessão pública conduzida por pregoeiro / agente.
SEM_EQUIPE_OBRIGATORIA = {"Inexigibilidade"}

CONSULTA_BASE = """
    SELECT l.*,
           a.nome AS agente_nome, m1.nome AS membro1_nome, m2.nome AS membro2_nome
      FROM licitacoes l
      LEFT JOIN servidores a  ON a.id  = l.agente_id
      LEFT JOIN servidores m1 ON m1.id = l.membro1_id
      LEFT JOIN servidores m2 ON m2.id = l.membro2_id
"""


def _buscar(id_):
    lic = get_db().execute(CONSULTA_BASE + " WHERE l.id = ?", (id_,)).fetchone()
    if lic is None:
        abort(404)
    return lic


def _servidores(incluir=()):
    """Servidores ativos, mais os já escalados na licitação (mesmo se inativos)."""
    ids = [i for i in incluir if i] or [0]
    return get_db().execute(
        f"SELECT * FROM servidores WHERE ativo = 1 OR id IN ({','.join('?' * len(ids))})"
        " ORDER BY nome",
        ids,
    ).fetchall()


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


def problemas_da_equipe(ids, servidores):
    """Regras de composição da equipe. Retorna a lista de problemas encontrados."""
    por_id = {s["id"]: s for s in servidores}
    escalados = [por_id[i] for i in ids if i in por_id]
    problemas = []
    if len({s["id"] for s in escalados}) < len(escalados):
        problemas.append("Um mesmo servidor foi escalado em mais de uma função na equipe.")
    nao_efetivos = [s for s in escalados if s["vinculo"] not in VINCULOS_EFETIVOS]
    # Equipe de 3: com 2 ou mais não efetivos, os efetivos ficam em minoria.
    if len(nao_efetivos) >= 2:
        nomes = " e ".join(s["nome"] for s in nao_efetivos)
        problemas.append(
            f"A equipe não pode ter minoria de servidores efetivos: {nomes} não são "
            "efetivos. Ao menos 2 dos 3 integrantes devem ser do quadro efetivo."
        )
    return problemas


def _validar(form, atual=None):
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

    atuais = [atual[c] for c in EQUIPE] if atual else []
    servidores = _servidores(atuais)
    validos = {s["id"] for s in servidores}
    for campo in EQUIPE:
        valor = dados[campo]
        dados[campo] = int(valor) if valor.isdigit() and int(valor) in validos else None
        if valor and dados[campo] is None:
            erros.append(f"{ROTULOS[campo]}: servidor inválido.")

    ids = [dados[c] for c in EQUIPE if dados[c]]
    exige_equipe = (dados["status"] != "Em planejamento"
                    and dados["modalidade"] not in SEM_EQUIPE_OBRIGATORIA)
    if exige_equipe and len(ids) < len(EQUIPE):
        erros.append("Informe a equipe completa: pregoeiro / agente de contratação e dois "
                     "membros.")
    erros += problemas_da_equipe(ids, servidores)

    for campo in ("numero_edital", "local", "observacoes"):
        dados[campo] = dados[campo] or None

    return dados, erros


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
        condicoes.append("? IN (l.agente_id, l.membro1_id, l.membro2_id)")
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
        " ORDER BY l.data_sessao",
        (agora, *com_sessao),
    ).fetchall()
    sessoes_hoje = [l for l in proximas if l["data_sessao"].startswith(hoje.isoformat())]
    suspensas = conn.execute(
        CONSULTA_BASE + " WHERE l.status = 'Suspensa' ORDER BY l.suspensa_em"
    ).fetchall()
    credenciamentos = conn.execute(
        CONSULTA_BASE + " WHERE l.modalidade = ? AND l.status = 'Em andamento'"
        " ORDER BY l.vigencia_ate",
        (CREDENCIAMENTO,),
    ).fetchall()
    atrasadas = conn.execute(
        CONSULTA_BASE + f" WHERE l.data_sessao < ? AND l.status IN ({_em(com_sessao)})"
        " ORDER BY l.data_sessao",
        (agora, *com_sessao),
    ).fetchall()
    contagem = dict(conn.execute(
        "SELECT status, COUNT(*) FROM licitacoes GROUP BY status"
    ).fetchall())

    return render_template(
        "agenda/painel.html", proximas=proximas, sessoes_hoje=sessoes_hoje,
        suspensas=suspensas, credenciamentos=credenciamentos, atrasadas=atrasadas,
        contagem=contagem, hoje=hoje.isoformat(),
        alerta_renovacao=(hoje + timedelta(days=30)).isoformat(),
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
            dia, rotulo = lic["vigencia_ate"], f"Renovar {lic['numero_edital'] or lic['numero_processo']}"
        else:
            dia = lic["data_sessao"][:10]
            rotulo = f"{lic['data_sessao'][11:16]} {lic['numero_edital'] or lic['numero_processo']}"
        eventos.setdefault(dia, []).append({"lic": lic, "rotulo": rotulo})

    anterior = date(ano, mes, 1) - timedelta(days=1)
    seguinte = date(ano, mes, 28) + timedelta(days=7)
    return render_template(
        "agenda/calendario.html",
        semanas=semanas, eventos=eventos, ano=ano, mes=mes, nome_mes=MESES[mes - 1],
        hoje=hoje, anterior=anterior, seguinte=seguinte,
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
        servidores=_servidores(), filtros=request.args,
    )


def _render_form(dados, titulo, atual=None):
    return render_template(
        "agenda/form.html", dados=dados, titulo=titulo, atual=atual,
        modalidades=MODALIDADES, servidores=_servidores([dados.get(c) for c in EQUIPE]),
        status_form=[s for s in STATUS if s not in STATUS_DA_ACAO_SUSPENDER
                     or (atual and atual["status"] == s)],
        status_credenciamento=STATUS_CREDENCIAMENTO, credenciamento=CREDENCIAMENTO,
        efetivos=VINCULOS_EFETIVOS,
    )


@bp.route("/licitacoes/nova", methods=["GET", "POST"])
@permissao("criar")
def nova():
    dados = {"status": "Em planejamento"}
    if request.method == "POST":
        dados, erros = _validar(request.form)
        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            conn = get_db()
            cur = conn.execute(
                f"INSERT INTO licitacoes ({', '.join(CAMPOS)}, criado_por)"
                f" VALUES ({_em(CAMPOS)}, ?)",
                (*[dados[c] for c in CAMPOS], g.usuario["id"]),
            )
            registrar("Cadastro de licitação", referencia=dados["numero_processo"],
                      licitacao_id=cur.lastrowid)
            conn.commit()
            flash("Licitação cadastrada.", "sucesso")
            return redirect(url_for("agenda.detalhe", id_=cur.lastrowid))

    return _render_form(dados, "Nova licitação")


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
    equipe = {s["id"]: s for s in _servidores(ids)}
    # A escala pode ter ficado irregular depois (ex.: mudança de vínculo de um servidor).
    alertas_equipe = problemas_da_equipe([i for i in ids if i], list(equipe.values()))
    return render_template(
        "agenda/detalhe.html", lic=lic, historico=historico, equipe=equipe,
        alertas_equipe=alertas_equipe, credenciamento=CREDENCIAMENTO, efetivos=VINCULOS_EFETIVOS,
        pode_suspender=_pode_suspender(lic),
        link_whatsapp=_link_whatsapp(_texto_whatsapp([lic])),
    )


@bp.route("/licitacoes/<int:id_>/editar", methods=["GET", "POST"])
@permissao("editar")
def editar(id_):
    lic = _buscar(id_)
    dados = dict(lic)
    if request.method == "POST":
        dados, erros = _validar(request.form, lic)
        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            alteracoes = _descrever_alteracoes(lic, dados)
            if alteracoes:
                conn = get_db()
                conn.execute(
                    f"UPDATE licitacoes SET {', '.join(c + ' = ?' for c in CAMPOS)},"
                    " atualizado_em = datetime('now', 'localtime') WHERE id = ?",
                    (*[dados[c] for c in CAMPOS], id_),
                )
                if lic["status"] == "Suspensa" and dados["status"] != "Suspensa":
                    conn.execute("UPDATE licitacoes SET suspensa_em = NULL,"
                                 " motivo_suspensao = NULL WHERE id = ?", (id_,))
                registrar("Alteração de licitação", referencia=dados["numero_processo"],
                          detalhes="; ".join(alteracoes), licitacao_id=id_)
                conn.commit()
                flash("Licitação atualizada.", "sucesso")
            else:
                flash("Nenhuma alteração foi feita.", "info")
            return redirect(url_for("agenda.detalhe", id_=id_))

    return _render_form(dados, f"Editar licitação {lic['numero_processo']}", lic)


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


def _pode_suspender(lic):
    return lic["modalidade"] != CREDENCIAMENTO and lic["status"] in STATUS_ABERTOS


@bp.route("/licitacoes/<int:id_>/suspender", methods=["GET", "POST"])
@permissao("suspender")
def suspender(id_):
    """Registra a suspensão sem data definida ou a remarcação com nova data e hora."""
    lic = _buscar(id_)
    if not _pode_suspender(lic):
        abort(400, "Esta licitação não pode ser suspensa ou remarcada na situação atual.")

    agora = datetime.now().strftime("%Y-%m-%dT%H:%M")
    dados = {"acao": "suspender", "suspensa_em": agora}
    if request.method == "POST":
        dados = {c: request.form.get(c, "").strip()
                 for c in ("acao", "suspensa_em", "nova_data", "motivo")}
        erros = []
        if dados["acao"] == "suspender":
            try:
                quando = _ler_data(dados["suspensa_em"], com_hora=True)
            except ValueError:
                erros.append("Informe a data e a hora da suspensão.")
        elif dados["acao"] == "remarcar":
            try:
                quando = _ler_data(dados["nova_data"], com_hora=True)
                if quando <= agora:
                    erros.append("A nova data e hora da sessão deve ser futura.")
            except ValueError:
                erros.append("Informe a nova data e a hora da sessão.")
        else:
            erros.append("Escolha entre suspender ou remarcar.")

        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            conn = get_db()
            motivo = dados["motivo"] or None
            if dados["acao"] == "suspender":
                conn.execute(
                    "UPDATE licitacoes SET status = 'Suspensa', suspensa_em = ?,"
                    " motivo_suspensao = ?, atualizado_em = datetime('now', 'localtime')"
                    " WHERE id = ?",
                    (quando, motivo, id_),
                )
                acao = "Sessão suspensa sem data definida"
                detalhes = f"Suspensa em {_formatar(quando)}"
            else:
                conn.execute(
                    "UPDATE licitacoes SET status = 'Remarcada', data_sessao = ?,"
                    " suspensa_em = NULL, motivo_suspensao = NULL,"
                    " atualizado_em = datetime('now', 'localtime') WHERE id = ?",
                    (quando, id_),
                )
                acao = "Sessão remarcada"
                detalhes = f"De {_formatar(lic['data_sessao'])} para {_formatar(quando)}"
            if motivo:
                detalhes += f". Motivo: {motivo}"
            registrar(acao, referencia=lic["numero_processo"], detalhes=detalhes,
                      licitacao_id=id_)
            conn.commit()
            flash(f"{acao}.", "sucesso")
            return redirect(url_for("agenda.detalhe", id_=id_))

    return render_template("agenda/suspender.html", lic=lic, dados=dados)


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
    registrar("Renovação do credenciamento", referencia=lic["numero_processo"],
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
    registrar("Exclusão de licitação", referencia=lic["numero_processo"],
              detalhes=f"{lic['modalidade']} — {lic['objeto'][:200]}")
    conn.commit()
    flash(f"Licitação {lic['numero_processo']} excluída.", "sucesso")
    return redirect(url_for("agenda.lista"))


def _texto_whatsapp(licitacoes, titulo=None):
    """Texto formatado para o WhatsApp (*negrito*, _itálico_)."""
    def quando(valor):
        return datetime.fromisoformat(valor).strftime("%d/%m/%Y às %H:%M")

    partes = []
    if titulo:
        partes.append(f"*{titulo}*\n_Atualizado em {datetime.now():%d/%m/%Y às %H:%M}_")
    for lic in licitacoes:
        nome = f"{lic['modalidade']} {lic['numero_edital'] or ''}".strip()
        linhas = [f"📌 *{nome}*", f"Processo: {lic['numero_processo']}",
                  f"Objeto: {lic['objeto']}"]
        if lic["modalidade"] == CREDENCIAMENTO:
            linhas.append("🟢 Credenciamento aberto — inscrições a qualquer tempo")
            if lic["vigencia_ate"]:
                linhas.append(f"Vigência até {_formatar(lic['vigencia_ate'])}")
        elif lic["status"] == "Suspensa":
            linhas.append("⏸️ *SUSPENSA* — sem nova data definida")
            if lic["suspensa_em"]:
                linhas.append(f"Suspensa em {quando(lic['suspensa_em'])}")
        elif lic["status"] == "Remarcada":
            linhas.append(f"🔁 *REMARCADA* para {quando(lic['data_sessao'])}")
        elif lic["data_sessao"]:
            linhas.append(f"🗓️ Sessão: {quando(lic['data_sessao'])}")
        if lic["local"]:
            linhas.append(f"📍 {lic['local']}")
        if lic["status"] not in STATUS_DA_ACAO_SUSPENDER and lic["modalidade"] != CREDENCIAMENTO:
            linhas.append(f"Situação: {lic['status']}")
        partes.append("\n".join(linhas))
    if titulo and not licitacoes:
        partes.append("Não há licitações abertas no momento.")
    return "\n\n".join(partes)


def _link_whatsapp(texto):
    # Abre o WhatsApp (aplicativo ou Web) para o usuário escolher o contato ou grupo.
    return "https://wa.me/?text=" + quote(texto)


@bp.route("/licitacoes/whatsapp")
@permissao("ver")
def whatsapp():
    """Licitações abertas ou em andamento, prontas para enviar pelo WhatsApp."""
    licitacoes = get_db().execute(
        CONSULTA_BASE + f" WHERE l.status IN ({_em(STATUS_DIVULGAVEIS)})"
        " ORDER BY l.modalidade = ?, COALESCE(l.data_sessao, l.vigencia_ate)",
        (*STATUS_DIVULGAVEIS, CREDENCIAMENTO),
    ).fetchall()
    titulo = f"Licitações abertas — {current_app.config['NOME_ORGAO']}"
    texto = _texto_whatsapp(licitacoes, titulo)
    return render_template("agenda/whatsapp.html", texto=texto, total=len(licitacoes),
                           link=_link_whatsapp(texto))


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
        identificacao = lic["numero_edital"] or lic["numero_processo"]
        descricao = f"Processo {lic['numero_processo']} — {lic['objeto']}"
        if lic["agente_nome"]:
            descricao += f"\nPregoeiro / agente: {lic['agente_nome']}"
        if lic["modalidade"] == CREDENCIAMENTO:
            if not lic["vigencia_ate"] or lic["status"] != "Em andamento":
                continue
            inicio = [f"DTSTART;VALUE=DATE:{lic['vigencia_ate'].replace('-', '')}"]
            resumo = f"Renovar credenciamento {identificacao}"
        elif lic["data_sessao"]:
            dt = datetime.fromisoformat(lic["data_sessao"])
            inicio = [f"DTSTART:{dt.strftime('%Y%m%dT%H%M%S')}", "DURATION:PT2H"]
            resumo = f"{lic['modalidade']} {identificacao}"
            if lic["status"] == "Suspensa":
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
