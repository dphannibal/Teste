"""Configurações: permissões dos perfis (só administrador) e parâmetros do sistema
(nome do órgão, modalidades, siglas, cores e situações)."""
import functools
import re
import unicodedata

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import parametros as P
from .auth import login_obrigatorio, permissao
from .db import get_db, registrar
from .perfis import FASES, FASES_DA_ACAO, PERFIL_TOTAL, PERFIS, PERMISSOES

bp = Blueprint("config", __name__, url_prefix="/admin")

FORMATO_COR = re.compile(r"^#[0-9a-fA-F]{6}$")
FORMATO_SIGLA = re.compile(r"^[A-Za-zÀ-ú]{1,6}$")
# Situações criadas pelo usuário não podem ocupar as fases das ações de suspender/remarcar.
FASES_LIVRES = [f for f in FASES if f not in FASES_DA_ACAO]


def somente_administrador(view):
    @functools.wraps(view)
    @login_obrigatorio
    def wrapper(*args, **kwargs):
        if g.usuario["perfil"] != PERFIL_TOTAL:
            abort(403)
        return view(*args, **kwargs)

    return wrapper


def _erros(lista):
    for e in lista:
        flash(e, "erro")
    return bool(lista)


@bp.route("/perfis", methods=["GET", "POST"])
@somente_administrador
def perfis():
    """Matriz de permissões por perfil. O administrador mantém sempre todas."""
    editaveis = [p for p in PERFIS if p != PERFIL_TOTAL]
    if request.method == "POST":
        conn = get_db()
        antes = P.permissoes()
        mudancas = []
        for perfil in editaveis:
            novas = {p for p in request.form.getlist(f"perm_{perfil}") if p in PERMISSOES}
            atuais = antes.get(perfil, set())
            if novas != atuais:
                conn.execute("DELETE FROM permissoes WHERE perfil = ?", (perfil,))
                conn.executemany("INSERT INTO permissoes VALUES (?, ?)",
                                 [(perfil, p) for p in sorted(novas)])
                ganhou = ", ".join(PERMISSOES[p] for p in PERMISSOES if p in novas - atuais)
                perdeu = ", ".join(PERMISSOES[p] for p in PERMISSOES if p in atuais - novas)
                partes = [f"+ {ganhou}" if ganhou else "", f"− {perdeu}" if perdeu else ""]
                mudancas.append(f"{PERFIS[perfil]}: " + "; ".join(x for x in partes if x))
        if mudancas:
            registrar("Alteração de permissões", referencia="Perfis",
                      detalhes=" | ".join(mudancas))
            conn.commit()
            P.invalidar()
            flash("Permissões atualizadas.", "sucesso")
        else:
            flash("Nenhuma alteração foi feita.", "info")
        return redirect(url_for("config.perfis"))

    return render_template("config/perfis.html", editaveis=editaveis,
                           permissoes=PERMISSOES, atuais=P.permissoes())


@bp.route("/parametros")
@permissao("parametros")
def parametros():
    conn = get_db()
    uso_modalidade = dict(conn.execute(
        "SELECT modalidade, COUNT(*) FROM licitacoes GROUP BY modalidade").fetchall())
    uso_situacao = dict(conn.execute(
        "SELECT status, COUNT(*) FROM licitacoes GROUP BY status").fetchall())
    return render_template(
        "config/parametros.html", modalidades=P.modalidades(), situacoes=P.situacoes(),
        uso_modalidade=uso_modalidade, uso_situacao=uso_situacao, fases=FASES,
    )


@bp.route("/parametros/geral", methods=["POST"])
@permissao("parametros")
def salvar_geral():
    nome = request.form.get("nome_orgao", "").strip()
    if _erros([] if nome else ["Informe o nome do órgão."]):
        return redirect(url_for("config.parametros"))
    antigo = P.nome_orgao()
    if nome != antigo:
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO configuracoes VALUES ('nome_orgao', ?)", (nome,))
        registrar("Alteração de parâmetro", referencia="Nome do órgão",
                  detalhes=f"{antigo} → {nome}")
        conn.commit()
        P.invalidar()
    flash("Nome do órgão salvo.", "sucesso")
    return redirect(url_for("config.parametros"))


# --- Modalidades -------------------------------------------------------------------------

@bp.route("/modalidades/nova", methods=["GET", "POST"], defaults={"id_": None})
@bp.route("/modalidades/<int:id_>/editar", methods=["GET", "POST"])
@permissao("parametros")
def modalidade(id_):
    conn = get_db()
    atual = None
    if id_ is not None:
        atual = conn.execute("SELECT * FROM modalidades WHERE id = ?", (id_,)).fetchone()
        if atual is None:
            abort(404)
    proxima = (conn.execute("SELECT MAX(ordem) FROM modalidades").fetchone()[0] or 0) + 1
    dados = dict(atual) if atual else {
        "cor": "#1d4f91", "ordem": proxima, "ativa": 1, "credenciamento": 0,
        "exige_equipe": 1, "rotulo_condutor": "Agente de contratação",
    }
    em_uso = atual and conn.execute(
        "SELECT COUNT(*) FROM licitacoes WHERE modalidade = ?", (atual["nome"],)).fetchone()[0]

    if request.method == "POST":
        f = request.form
        dados = {
            "nome": f.get("nome", "").strip(), "sigla": f.get("sigla", "").strip().upper(),
            "cor": f.get("cor", "").strip(), "ordem": f.get("ordem", "0").strip(),
            "ativa": 1 if f.get("ativa") else 0,
            "credenciamento": 1 if f.get("credenciamento") else 0,
            "exige_equipe": 1 if f.get("exige_equipe") else 0,
            "rotulo_condutor": f.get("rotulo_condutor", "").strip() or "Agente de contratação",
        }
        erros = []
        if not dados["nome"]:
            erros.append("Informe o nome da modalidade.")
        elif conn.execute("SELECT 1 FROM modalidades WHERE nome = ? AND id != ?",
                          (dados["nome"], id_ or 0)).fetchone():
            erros.append("Já existe uma modalidade com esse nome.")
        if not FORMATO_SIGLA.match(dados["sigla"]):
            erros.append("A sigla deve ter de 1 a 6 letras (ex.: PE).")
        if not FORMATO_COR.match(dados["cor"]):
            erros.append("Escolha uma cor válida.")
        if not dados["ordem"].lstrip("-").isdigit():
            erros.append("A ordem deve ser um número.")
        if em_uso and dados["credenciamento"] != atual["credenciamento"]:
            erros.append("Não é possível mudar o tipo (credenciamento ou com sessão) de uma "
                         "modalidade já usada em licitações.")

        if not _erros(erros):
            valores = (dados["nome"], dados["sigla"], dados["cor"], int(dados["ordem"]),
                       dados["ativa"], dados["credenciamento"], dados["exige_equipe"],
                       dados["rotulo_condutor"])
            colunas = ("nome = ?, sigla = ?, cor = ?, ordem = ?, ativa = ?, credenciamento = ?,"
                       " exige_equipe = ?, rotulo_condutor = ?")
            if atual is None:
                conn.execute(f"INSERT INTO modalidades (nome, sigla, cor, ordem, ativa,"
                             " credenciamento, exige_equipe, rotulo_condutor)"
                             " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", valores)
                registrar("Cadastro de modalidade", referencia=dados["nome"],
                          detalhes=f"Sigla {dados['sigla']}")
            else:
                conn.execute(f"UPDATE modalidades SET {colunas} WHERE id = ?", (*valores, id_))
                if dados["nome"] != atual["nome"]:
                    # As licitações guardam o nome da modalidade.
                    conn.execute("UPDATE licitacoes SET modalidade = ? WHERE modalidade = ?",
                                 (dados["nome"], atual["nome"]))
                mudancas = [f"{rotulo}: {atual[c]} → {dados[c]}" for c, rotulo in (
                    ("nome", "Nome"), ("sigla", "Sigla"), ("cor", "Cor"), ("ativa", "Ativa"),
                    ("exige_equipe", "Exige equipe"), ("rotulo_condutor", "Condutor"))
                    if str(atual[c]) != str(dados[c])]
                registrar("Alteração de modalidade", referencia=dados["nome"],
                          detalhes="; ".join(mudancas) or None)
            conn.commit()
            P.invalidar()
            flash("Modalidade salva.", "sucesso")
            return redirect(url_for("config.parametros"))

    return render_template("config/modalidade.html", dados=dados, novo=atual is None,
                           em_uso=em_uso)


@bp.route("/modalidades/<int:id_>/excluir", methods=["POST"])
@permissao("parametros")
def excluir_modalidade(id_):
    conn = get_db()
    atual = conn.execute("SELECT * FROM modalidades WHERE id = ?", (id_,)).fetchone()
    if atual is None:
        abort(404)
    if conn.execute("SELECT 1 FROM licitacoes WHERE modalidade = ?", (atual["nome"],)).fetchone():
        flash("Modalidade em uso: desative-a em vez de excluir.", "erro")
    else:
        conn.execute("DELETE FROM modalidades WHERE id = ?", (id_,))
        registrar("Exclusão de modalidade", referencia=atual["nome"])
        conn.commit()
        P.invalidar()
        flash("Modalidade excluída.", "sucesso")
    return redirect(url_for("config.parametros"))


# --- Situações ---------------------------------------------------------------------------

def _chave_para(nome):
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_") or "situacao"
    chave, n = base, 2
    while get_db().execute("SELECT 1 FROM situacoes WHERE chave = ?", (chave,)).fetchone():
        chave, n = f"{base}_{n}", n + 1
    return chave


@bp.route("/situacoes/nova", methods=["GET", "POST"], defaults={"chave": None})
@bp.route("/situacoes/<chave>/editar", methods=["GET", "POST"])
@permissao("parametros")
def situacao(chave):
    conn = get_db()
    atual = None
    if chave is not None:
        atual = conn.execute("SELECT * FROM situacoes WHERE chave = ?", (chave,)).fetchone()
        if atual is None:
            abort(404)
    proxima = (conn.execute("SELECT MAX(ordem) FROM situacoes").fetchone()[0] or 0) + 1
    dados = dict(atual) if atual else {"cor": "#475467", "fase": "encerrada", "ordem": proxima,
                                       "ativa": 1, "sistema": 0}

    if request.method == "POST":
        f = request.form
        sistema = bool(atual and atual["sistema"])
        dados = {
            "nome": f.get("nome", "").strip(), "cor": f.get("cor", "").strip(),
            "ordem": f.get("ordem", "0").strip(),
            # As do sistema não mudam de fase nem podem ser desativadas.
            "fase": atual["fase"] if sistema else f.get("fase", ""),
            "ativa": 1 if sistema or f.get("ativa") else 0,
            "sistema": int(sistema),
        }
        erros = []
        if not dados["nome"]:
            erros.append("Informe o nome da situação.")
        elif conn.execute("SELECT 1 FROM situacoes WHERE nome = ? AND chave != ?",
                          (dados["nome"], chave or "")).fetchone():
            erros.append("Já existe uma situação com esse nome.")
        if not FORMATO_COR.match(dados["cor"]):
            erros.append("Escolha uma cor válida.")
        if not sistema and dados["fase"] not in FASES_LIVRES:
            erros.append("Escolha a fase da situação.")
        if not dados["ordem"].lstrip("-").isdigit():
            erros.append("A ordem deve ser um número.")

        if not _erros(erros):
            if atual is None:
                conn.execute(
                    "INSERT INTO situacoes (chave, nome, cor, fase, ordem, ativa)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (_chave_para(dados["nome"]), dados["nome"], dados["cor"], dados["fase"],
                     int(dados["ordem"]), dados["ativa"]),
                )
                registrar("Cadastro de situação", referencia=dados["nome"],
                          detalhes=f"Fase: {FASES[dados['fase']]}")
            else:
                conn.execute(
                    "UPDATE situacoes SET nome = ?, cor = ?, fase = ?, ordem = ?, ativa = ?"
                    " WHERE chave = ?",
                    (dados["nome"], dados["cor"], dados["fase"], int(dados["ordem"]),
                     dados["ativa"], chave),
                )
                mudancas = [f"{rotulo}: {atual[c]} → {dados[c]}" for c, rotulo in (
                    ("nome", "Nome"), ("cor", "Cor"), ("fase", "Fase"), ("ativa", "Ativa"))
                    if str(atual[c]) != str(dados[c])]
                registrar("Alteração de situação", referencia=dados["nome"],
                          detalhes="; ".join(mudancas) or None)
            conn.commit()
            P.invalidar()
            flash("Situação salva.", "sucesso")
            return redirect(url_for("config.parametros"))

    return render_template("config/situacao.html", dados=dados, novo=atual is None,
                           fases={f: FASES[f] for f in FASES_LIVRES}, todas_fases=FASES)


@bp.route("/situacoes/<chave>/excluir", methods=["POST"])
@permissao("parametros")
def excluir_situacao(chave):
    conn = get_db()
    atual = conn.execute("SELECT * FROM situacoes WHERE chave = ?", (chave,)).fetchone()
    if atual is None:
        abort(404)
    if atual["sistema"]:
        flash("Situação usada pelo sistema: pode ser renomeada, mas não excluída.", "erro")
    elif conn.execute("SELECT 1 FROM licitacoes WHERE status = ?", (chave,)).fetchone():
        flash("Situação em uso: desative-a em vez de excluir.", "erro")
    else:
        conn.execute("DELETE FROM situacoes WHERE chave = ?", (chave,))
        registrar("Exclusão de situação", referencia=atual["nome"])
        conn.commit()
        P.invalidar()
        flash("Situação excluída.", "sucesso")
    return redirect(url_for("config.parametros"))
