"""Administração de usuários e trilha de auditoria."""
import re
import secrets

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from .auth import permissao
from .db import get_db, registrar
from .perfis import DESCRICAO_PERFIS, PERFIS

bp = Blueprint("admin", __name__, url_prefix="/admin")

FORMATO_LOGIN = re.compile(r"^[a-zA-Z0-9._-]{3,40}$")
ITENS_POR_PAGINA = 50


def _buscar_usuario(id_):
    usuario = get_db().execute("SELECT * FROM usuarios WHERE id = ?", (id_,)).fetchone()
    if usuario is None:
        abort(404)
    return usuario


def _senha_temporaria():
    return secrets.token_urlsafe(9)


@bp.route("/usuarios")
@permissao("usuarios")
def usuarios():
    lista = get_db().execute("SELECT * FROM usuarios ORDER BY ativo DESC, nome").fetchall()
    return render_template("admin/usuarios.html", usuarios=lista, descricoes=DESCRICAO_PERFIS)


@bp.route("/usuarios/novo", methods=["GET", "POST"])
@permissao("usuarios")
def novo_usuario():
    dados = {"perfil": "consulta"}
    if request.method == "POST":
        dados = {c: request.form.get(c, "").strip() for c in ("nome", "login", "email", "perfil")}
        conn = get_db()
        erros = []
        if not dados["nome"]:
            erros.append("Informe o nome.")
        if not FORMATO_LOGIN.match(dados["login"]):
            erros.append("Login deve ter de 3 a 40 caracteres: letras, números, ponto, hífen ou _.")
        elif conn.execute("SELECT 1 FROM usuarios WHERE login = ?", (dados["login"],)).fetchone():
            erros.append("Já existe um usuário com esse login.")
        if dados["perfil"] not in PERFIS:
            erros.append("Selecione um perfil válido.")

        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            senha = _senha_temporaria()
            conn.execute(
                "INSERT INTO usuarios (nome, login, email, senha_hash, perfil, trocar_senha)"
                " VALUES (?, ?, ?, ?, ?, 1)",
                (dados["nome"], dados["login"], dados["email"] or None,
                 generate_password_hash(senha), dados["perfil"]),
            )
            registrar("Cadastro de usuário", referencia=dados["login"],
                      detalhes=f"Perfil: {PERFIS[dados['perfil']]}")
            conn.commit()
            flash(f"Usuário criado. Senha temporária de “{dados['login']}”: {senha} — "
                  "anote e entregue ao usuário; ela será trocada no primeiro acesso.", "sucesso")
            return redirect(url_for("admin.usuarios"))

    return render_template("admin/usuario_form.html", dados=dados, descricoes=DESCRICAO_PERFIS,
                           novo=True)


@bp.route("/usuarios/<int:id_>/editar", methods=["GET", "POST"])
@permissao("usuarios")
def editar_usuario(id_):
    usuario = _buscar_usuario(id_)
    dados = dict(usuario)
    if request.method == "POST":
        dados.update({c: request.form.get(c, "").strip() for c in ("nome", "email", "perfil")})
        dados["ativo"] = 1 if request.form.get("ativo") else 0
        proprio = usuario["id"] == g.usuario["id"]

        erros = []
        if not dados["nome"]:
            erros.append("Informe o nome.")
        if dados["perfil"] not in PERFIS:
            erros.append("Selecione um perfil válido.")
        if proprio and (dados["perfil"] != "administrador" or not dados["ativo"]):
            erros.append("Você não pode remover o próprio acesso de administrador.")

        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            mudancas = []
            if dados["perfil"] != usuario["perfil"]:
                mudancas.append(f"Perfil: {PERFIS[usuario['perfil']]} → {PERFIS[dados['perfil']]}")
            if dados["ativo"] != usuario["ativo"]:
                mudancas.append("Reativado" if dados["ativo"] else "Desativado")
            if dados["nome"] != usuario["nome"]:
                mudancas.append(f"Nome: {usuario['nome']} → {dados['nome']}")
            if (dados["email"] or None) != usuario["email"]:
                mudancas.append("E-mail alterado")

            conn = get_db()
            conn.execute(
                "UPDATE usuarios SET nome = ?, email = ?, perfil = ?, ativo = ? WHERE id = ?",
                (dados["nome"], dados["email"] or None, dados["perfil"], dados["ativo"], id_),
            )
            if mudancas:
                registrar("Alteração de usuário", referencia=usuario["login"],
                          detalhes="; ".join(mudancas))
            conn.commit()
            flash("Usuário atualizado.", "sucesso")
            return redirect(url_for("admin.usuarios"))

    return render_template("admin/usuario_form.html", dados=dados, descricoes=DESCRICAO_PERFIS,
                           novo=False)


@bp.route("/usuarios/<int:id_>/redefinir-senha", methods=["POST"])
@permissao("usuarios")
def redefinir_senha(id_):
    usuario = _buscar_usuario(id_)
    senha = _senha_temporaria()
    conn = get_db()
    conn.execute(
        "UPDATE usuarios SET senha_hash = ?, trocar_senha = 1 WHERE id = ?",
        (generate_password_hash(senha), id_),
    )
    registrar("Redefinição de senha", referencia=usuario["login"])
    conn.commit()
    flash(f"Nova senha temporária de “{usuario['login']}”: {senha}", "sucesso")
    return redirect(url_for("admin.usuarios"))


@bp.route("/auditoria")
@permissao("auditoria")
def auditoria():
    pagina = max(request.args.get("pagina", 1, type=int), 1)
    registros = get_db().execute(
        "SELECT h.*, u.nome AS usuario_nome, l.numero_processo"
        "  FROM historico h"
        "  LEFT JOIN usuarios u ON u.id = h.usuario_id"
        "  LEFT JOIN licitacoes l ON l.id = h.licitacao_id"
        " ORDER BY h.id DESC LIMIT ? OFFSET ?",
        (ITENS_POR_PAGINA + 1, (pagina - 1) * ITENS_POR_PAGINA),
    ).fetchall()
    tem_mais = len(registros) > ITENS_POR_PAGINA
    return render_template("admin/auditoria.html", registros=registros[:ITENS_POR_PAGINA],
                           pagina=pagina, tem_mais=tem_mais)
