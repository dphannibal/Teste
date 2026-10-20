import re

import pytest
from werkzeug.security import generate_password_hash

from licitacoes import create_app, garantir_admin_inicial
from licitacoes.db import get_db

SENHA = "senha-segura-1"


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "teste.sqlite3"),
                      "SECRET_KEY": "teste"})
    with app.app_context():
        conn = get_db()
        for perfil in ("administrador", "gestor", "operador", "consulta"):
            conn.execute(
                "INSERT INTO usuarios (nome, login, senha_hash, perfil, trocar_senha)"
                " VALUES (?, ?, ?, ?, 0)",
                (perfil.title(), perfil, generate_password_hash(SENHA), perfil),
            )
        conn.commit()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, url):
    html = client.get(url).get_data(as_text=True)
    return re.search(r'name="_csrf" value="([^"]+)"', html).group(1)


def entrar(client, login, senha=SENHA):
    token = csrf(client, "/login")
    return client.post("/login", data={"login": login, "senha": senha, "_csrf": token})


def post(client, url, dados, pagina=None):
    dados = dict(dados, _csrf=csrf(client, pagina or "/"))
    return client.post(url, data=dados)


LICITACAO = {
    "numero_processo": "2026.000123",
    "numero_edital": "PE 010/2026",
    "modalidade": "Pregão Eletrônico",
    "objeto": "Aquisição de material de expediente",
    "data_sessao": "2026-11-05T09:30",
    "local": "Compras.gov.br",
    "valor_estimado": "150.000,50",
    "status": "Edital publicado",
}


def criar_licitacao(client):
    resp = post(client, "/licitacoes/nova", LICITACAO, "/licitacoes/nova")
    assert resp.status_code == 302
    return int(resp.headers["Location"].rsplit("/", 1)[1])


def test_exige_login(client):
    resp = client.get("/")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_login_invalido(client):
    resp = entrar(client, "gestor", "errada")
    assert "Usuário ou senha inválidos" in resp.get_data(as_text=True)


def test_post_sem_csrf_e_rejeitado(client):
    resp = client.post("/login", data={"login": "gestor", "senha": SENHA})
    assert resp.status_code == 400


def test_operador_cria_e_edita_mas_nao_exclui(client):
    entrar(client, "operador")
    id_ = criar_licitacao(client)

    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "R$ 150.000,50" in pagina
    assert "Excluir" not in pagina

    dados = dict(LICITACAO, status="Homologada")
    resp = post(client, f"/licitacoes/{id_}/editar", dados, f"/licitacoes/{id_}/editar")
    assert resp.status_code == 302
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Situação: Edital publicado → Homologada" in pagina

    resp = post(client, f"/licitacoes/{id_}/excluir", {})
    assert resp.status_code == 403


def test_consulta_so_visualiza(client):
    entrar(client, "gestor")
    id_ = criar_licitacao(client)
    client.post("/logout", data={"_csrf": csrf(client, "/")})

    entrar(client, "consulta")
    assert client.get("/calendario?ano=2026&mes=11").status_code == 200
    assert "PE 010/2026" in client.get("/calendario?ano=2026&mes=11").get_data(as_text=True)
    assert client.get(f"/licitacoes/{id_}").status_code == 200
    assert client.get("/licitacoes/nova").status_code == 403
    assert client.get(f"/licitacoes/{id_}/editar").status_code == 403
    assert client.get("/admin/usuarios").status_code == 403
    assert client.get("/admin/auditoria").status_code == 403


def test_gestor_exclui_e_ve_auditoria(client):
    entrar(client, "gestor")
    id_ = criar_licitacao(client)
    resp = post(client, f"/licitacoes/{id_}/excluir", {})
    assert resp.status_code == 302
    assert client.get(f"/licitacoes/{id_}").status_code == 404

    auditoria = client.get("/admin/auditoria").get_data(as_text=True)
    assert "Exclusão de licitação" in auditoria
    assert client.get("/admin/usuarios").status_code == 403


def test_validacao_de_campos(client):
    entrar(client, "operador")
    dados = dict(LICITACAO, modalidade="Inventada", valor_estimado="abc", objeto="")
    resp = post(client, "/licitacoes/nova", dados, "/licitacoes/nova")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "modalidade válida" in html and "Valor estimado inválido" in html


def test_filtros_e_exportacao_ics(client):
    entrar(client, "operador")
    criar_licitacao(client)
    post(client, "/licitacoes/nova",
         dict(LICITACAO, numero_processo="2026.999", modalidade="Leilão", numero_edital=""),
         "/licitacoes/nova")

    html = client.get("/licitacoes?modalidade=Leilão").get_data(as_text=True)
    assert "2026.999" in html and "2026.000123" not in html

    ics = client.get("/licitacoes.ics").get_data(as_text=True)
    assert ics.count("BEGIN:VEVENT") == 2
    assert "DTSTART:20261105T093000" in ics


def test_admin_gerencia_usuarios(client, app):
    entrar(client, "administrador")
    resp = post(client, "/admin/usuarios/novo",
                {"nome": "Maria Silva", "login": "maria.silva", "perfil": "operador"},
                "/admin/usuarios/novo")
    html = client.get(resp.headers["Location"]).get_data(as_text=True)
    senha = re.search(r"Senha temporária de “maria.silva”: (\S+)", html).group(1)

    # Admin não pode rebaixar a si mesmo.
    with app.app_context():
        admin_id = get_db().execute("SELECT id FROM usuarios WHERE login='administrador'").fetchone()[0]
    resp = post(client, f"/admin/usuarios/{admin_id}/editar",
                {"nome": "Adm", "perfil": "consulta", "ativo": "1"}, "/admin/usuarios")
    assert "próprio acesso de administrador" in resp.get_data(as_text=True)

    # Novo usuário é obrigado a trocar a senha temporária.
    novo = app.test_client()
    entrar(novo, "maria.silva", senha)
    resp = novo.get("/licitacoes")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/senha")
    post(novo, "/senha", {"senha_atual": senha, "nova_senha": "nova-senha-123",
                          "confirmacao": "nova-senha-123"}, "/senha")
    assert novo.get("/licitacoes").status_code == 200


def test_usuario_desativado_perde_acesso(client, app):
    outro = app.test_client()
    entrar(outro, "consulta")
    assert outro.get("/").status_code == 200

    entrar(client, "administrador")
    with app.app_context():
        uid = get_db().execute("SELECT id FROM usuarios WHERE login='consulta'").fetchone()[0]
    post(client, f"/admin/usuarios/{uid}/editar",
         {"nome": "Consulta", "perfil": "consulta"}, "/admin/usuarios")

    assert outro.get("/").status_code == 302
    assert "desativado" in entrar(outro, "consulta").get_data(as_text=True)


def test_admin_inicial(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "vazio.sqlite3")})
    senha = garantir_admin_inicial(app)
    assert senha and garantir_admin_inicial(app) is None
    client = app.test_client()
    resp = entrar(client, "admin", senha)
    assert resp.headers["Location"] == "/"
    assert client.get("/").headers["Location"].endswith("/senha")
