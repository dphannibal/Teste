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
        for nome, vinculo in (("Ana Efetiva", "efetivo"), ("Beto Efetivo", "efetivo"),
                              ("Caio Comissionado", "comissionado"),
                              ("Dora Temporária", "temporario")):
            conn.execute("INSERT INTO servidores (nome, vinculo) VALUES (?, ?)", (nome, vinculo))
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
    "data_publicacao": "2026-09-01",
    # Servidores 1 e 2 são efetivos; 3 e 4 não.
    "agente_id": "1",
    "membro1_id": "2",
    "membro2_id": "3",
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


def test_equipe_com_minoria_efetiva_e_rejeitada(client):
    entrar(client, "operador")
    dados = dict(LICITACAO, membro1_id="3", membro2_id="4")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "minoria de servidores efetivos" in html
    assert "Caio Comissionado e Dora Temporária" in html

    dados = dict(LICITACAO, membro1_id="1")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "mais de uma função" in html


def test_equipe_completa_exigida_fora_do_planejamento(client):
    entrar(client, "operador")
    dados = dict(LICITACAO, membro2_id="")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "equipe completa" in html

    dados = dict(LICITACAO, membro2_id="", status="Em planejamento", data_sessao="")
    assert post(client, "/licitacoes/nova", dados, "/licitacoes/nova").status_code == 302


def test_credenciamento_aberto_e_renovado_anualmente(client):
    entrar(client, "gestor")
    dados = dict(LICITACAO, modalidade="Credenciamento", numero_edital="CR 001/2026",
                 data_publicacao="2026-03-10", status="Edital publicado")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "Credenciamento só pode estar" in html

    dados["status"] = "Em andamento"
    id_ = int(post(client, "/licitacoes/nova", dados, "/licitacoes/nova")
              .headers["Location"].rsplit("/", 1)[1])
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "10/03/2027" in pagina  # vigência padrão: 1 ano após a publicação
    assert "Suspender / remarcar" not in pagina

    post(client, f"/licitacoes/{id_}/renovar", {})
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "10/03/2028" in pagina and "Renovação do credenciamento" in pagina
    assert "Credenciamentos abertos" in client.get("/").get_data(as_text=True)
    assert "Credenciamento aberto" in client.get("/licitacoes/whatsapp").get_data(as_text=True)


def test_operador_suspende_e_remarca(client):
    entrar(client, "operador")
    id_ = criar_licitacao(client)

    # Suspensão não é feita pelo formulário comum.
    html = post(client, f"/licitacoes/{id_}/editar", dict(LICITACAO, status="Suspensa"),
                f"/licitacoes/{id_}/editar").get_data(as_text=True)
    assert "Suspender / remarcar" in html

    url = f"/licitacoes/{id_}/suspender"
    post(client, url, {"acao": "suspender", "suspensa_em": "2026-10-20T14:35",
                       "motivo": "Impugnação do edital"}, url)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Sessão suspensa sem data definida" in pagina and "20/10/2026 14:35" in pagina
    assert "Suspensas sem data definida" in client.get("/").get_data(as_text=True)

    html = post(client, url, {"acao": "remarcar", "nova_data": "2020-01-01T10:00"}, url)
    assert "deve ser futura" in html.get_data(as_text=True)
    post(client, url, {"acao": "remarcar", "nova_data": "2030-02-15T10:00"}, url)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Remarcada" in pagina and "15/02/2030 10:00" in pagina
    assert "De 05/11/2026 09:30 para 15/02/2030 10:00" in pagina


def test_consulta_nao_suspende(client):
    entrar(client, "gestor")
    id_ = criar_licitacao(client)
    client.post("/logout", data={"_csrf": csrf(client, "/")})
    entrar(client, "consulta")
    assert client.get(f"/licitacoes/{id_}/suspender").status_code == 403


def test_whatsapp_lista_somente_abertas(client):
    entrar(client, "operador")
    criar_licitacao(client)
    post(client, "/licitacoes/nova", dict(LICITACAO, numero_processo="2026.HOMOLOG",
                                          status="Homologada"), "/licitacoes/nova")
    post(client, "/licitacoes/nova", dict(LICITACAO, numero_processo="2026.PLANEJ",
                                          status="Em planejamento"), "/licitacoes/nova")
    html = client.get("/licitacoes/whatsapp").get_data(as_text=True)
    assert "2026.000123" in html and "Sessão: 05/11/2026 às 09:30" in html
    assert "2026.HOMOLOG" not in html and "2026.PLANEJ" not in html
    assert "https://wa.me/?text=" in html


def test_painel_mostra_sessoes_alem_de_30_dias(client):
    entrar(client, "operador")
    post(client, "/licitacoes/nova", dict(LICITACAO, numero_processo="2027.LONGE",
                                          data_sessao="2027-06-01T09:00"), "/licitacoes/nova")
    assert "2027.LONGE" in client.get("/").get_data(as_text=True)
