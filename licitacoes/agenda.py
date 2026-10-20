"""Agenda, calendário e cadastro de licitações."""
import calendar
from datetime import date, datetime, timedelta

from flask import (
    Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for,
)

from .auth import permissao
from .db import get_db, registrar
from .perfis import MODALIDADES, STATUS, STATUS_ABERTOS

bp = Blueprint("agenda", __name__)

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

CAMPOS = ["numero_processo", "numero_edital", "modalidade", "objeto", "data_sessao",
          "local", "responsavel_id", "valor_estimado", "status", "observacoes"]

ROTULOS = {
    "numero_processo": "Nº do processo",
    "numero_edital": "Nº do edital",
    "modalidade": "Modalidade",
    "objeto": "Objeto",
    "data_sessao": "Data da sessão",
    "local": "Local / plataforma",
    "responsavel_id": "Responsável",
    "valor_estimado": "Valor estimado",
    "status": "Situação",
    "observacoes": "Observações",
}

CONSULTA_BASE = """
    SELECT l.*, u.nome AS responsavel_nome
      FROM licitacoes l
      LEFT JOIN usuarios u ON u.id = l.responsavel_id
"""


def _buscar(id_):
    lic = get_db().execute(CONSULTA_BASE + " WHERE l.id = ?", (id_,)).fetchone()
    if lic is None:
        abort(404)
    return lic


def _responsaveis(incluir=None):
    """Usuários que podem conduzir licitações (mais o responsável atual, se houver)."""
    return get_db().execute(
        "SELECT id, nome FROM usuarios WHERE (ativo = 1 AND perfil != 'consulta') OR id = ?"
        " ORDER BY nome",
        (incluir,),
    ).fetchall()


def _ler_valor(texto):
    """Aceita '1.234,56', '1234,56' ou '1234.56'."""
    texto = texto.strip().replace("R$", "").replace(" ", "")
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return round(float(texto), 2)


def _validar(form, responsavel_atual=None):
    dados = {c: form.get(c, "").strip() for c in CAMPOS}
    erros = []

    for campo in ("numero_processo", "objeto", "data_sessao"):
        if not dados[campo]:
            erros.append(f"Informe o campo “{ROTULOS[campo]}”.")
    if dados["modalidade"] not in MODALIDADES:
        erros.append("Selecione uma modalidade válida.")
    if dados["status"] not in STATUS:
        erros.append("Selecione uma situação válida.")

    if dados["data_sessao"]:
        try:
            dados["data_sessao"] = datetime.fromisoformat(dados["data_sessao"]).strftime(
                "%Y-%m-%dT%H:%M"
            )
        except ValueError:
            erros.append("Data da sessão inválida.")

    try:
        dados["valor_estimado"] = _ler_valor(dados["valor_estimado"])
        if dados["valor_estimado"] is not None and dados["valor_estimado"] < 0:
            erros.append("O valor estimado não pode ser negativo.")
    except ValueError:
        erros.append("Valor estimado inválido. Use, por exemplo, 150.000,00.")

    if dados["responsavel_id"]:
        ids_validos = {str(r["id"]) for r in _responsaveis(responsavel_atual)}
        if dados["responsavel_id"] not in ids_validos:
            erros.append("Responsável inválido.")
        else:
            dados["responsavel_id"] = int(dados["responsavel_id"])
    else:
        dados["responsavel_id"] = None

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
    if args.get("responsavel", "").isdigit():
        condicoes.append("l.responsavel_id = ?")
        params.append(int(args["responsavel"]))
    if args.get("de"):
        condicoes.append("l.data_sessao >= ?")
        params.append(args["de"])
    if args.get("ate"):
        condicoes.append("l.data_sessao < ?")
        params.append(args["ate"] + "T99")  # inclui o dia inteiro
    where = (" WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return where, params


@bp.route("/")
@permissao("ver")
def painel():
    conn = get_db()
    agora = datetime.now().strftime("%Y-%m-%dT%H:%M")
    limite = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M")
    marcadores = ",".join("?" * len(STATUS_ABERTOS))

    proximas = conn.execute(
        CONSULTA_BASE + f" WHERE l.data_sessao BETWEEN ? AND ? AND l.status IN ({marcadores})"
        " ORDER BY l.data_sessao",
        (agora, limite, *STATUS_ABERTOS),
    ).fetchall()
    hoje = date.today().isoformat()
    sessoes_hoje = [l for l in proximas if l["data_sessao"].startswith(hoje)]
    atrasadas = conn.execute(
        CONSULTA_BASE + f" WHERE l.data_sessao < ? AND l.status IN ({marcadores})"
        " ORDER BY l.data_sessao",
        (agora, *STATUS_ABERTOS),
    ).fetchall()
    contagem = dict(conn.execute(
        "SELECT status, COUNT(*) FROM licitacoes GROUP BY status"
    ).fetchall())

    return render_template(
        "agenda/painel.html",
        proximas=proximas, sessoes_hoje=sessoes_hoje, atrasadas=atrasadas, contagem=contagem,
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
    inicio, fim = semanas[0][0], semanas[-1][-1] + timedelta(days=1)
    eventos = {}
    for lic in get_db().execute(
        CONSULTA_BASE + " WHERE l.data_sessao >= ? AND l.data_sessao < ? ORDER BY l.data_sessao",
        (inicio.isoformat(), fim.isoformat()),
    ):
        eventos.setdefault(lic["data_sessao"][:10], []).append(lic)

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
        CONSULTA_BASE + where + " ORDER BY l.data_sessao DESC", params
    ).fetchall()
    return render_template(
        "agenda/lista.html", licitacoes=licitacoes, modalidades=MODALIDADES,
        responsaveis=_responsaveis(), filtros=request.args,
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
                f" VALUES ({', '.join('?' * len(CAMPOS))}, ?)",
                (*[dados[c] for c in CAMPOS], g.usuario["id"]),
            )
            registrar("Cadastro de licitação", referencia=dados["numero_processo"],
                      licitacao_id=cur.lastrowid)
            conn.commit()
            flash("Licitação cadastrada.", "sucesso")
            return redirect(url_for("agenda.detalhe", id_=cur.lastrowid))

    return render_template(
        "agenda/form.html", dados=dados, modalidades=MODALIDADES,
        responsaveis=_responsaveis(), titulo="Nova licitação",
    )


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
    return render_template("agenda/detalhe.html", lic=lic, historico=historico)


@bp.route("/licitacoes/<int:id_>/editar", methods=["GET", "POST"])
@permissao("editar")
def editar(id_):
    lic = _buscar(id_)
    dados = dict(lic)
    if request.method == "POST":
        dados, erros = _validar(request.form, lic["responsavel_id"])
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
                registrar("Alteração de licitação", referencia=dados["numero_processo"],
                          detalhes="; ".join(alteracoes), licitacao_id=id_)
                conn.commit()
                flash("Licitação atualizada.", "sucesso")
            else:
                flash("Nenhuma alteração foi feita.", "info")
            return redirect(url_for("agenda.detalhe", id_=id_))

    return render_template(
        "agenda/form.html", dados=dados, modalidades=MODALIDADES,
        responsaveis=_responsaveis(lic["responsavel_id"]), titulo=f"Editar licitação {lic['numero_processo']}",
    )


def _descrever_alteracoes(antes, depois):
    nomes = {r["id"]: r["nome"] for r in get_db().execute("SELECT id, nome FROM usuarios")}
    alteracoes = []
    for campo in CAMPOS:
        a, d = antes[campo], depois[campo]
        if a == d:
            continue
        if campo == "responsavel_id":
            a, d = nomes.get(a, "—"), nomes.get(d, "—")
        elif campo in ("objeto", "observacoes"):
            alteracoes.append(f"{ROTULOS[campo]} alterado")
            continue
        alteracoes.append(f"{ROTULOS[campo]}: {a if a is not None else '—'} → "
                          f"{d if d is not None else '—'}")
    return alteracoes


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
        inicio = datetime.fromisoformat(lic["data_sessao"])
        descricao = f"Processo {lic['numero_processo']} — {lic['objeto']}"
        if lic["responsavel_nome"]:
            descricao += f"\nResponsável: {lic['responsavel_nome']}"
        linhas += [
            "BEGIN:VEVENT",
            f"UID:licitacao-{lic['id']}@agenda-licitacoes",
            f"DTSTAMP:{carimbo}",
            f"DTSTART:{inicio.strftime('%Y%m%dT%H%M%S')}",
            "DURATION:PT2H",
            f"SUMMARY:{esc(lic['modalidade'] + ' ' + (lic['numero_edital'] or lic['numero_processo']))}",
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
