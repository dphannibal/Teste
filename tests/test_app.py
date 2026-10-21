import io
import re
from datetime import date, timedelta

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
                              ("Dora Temporária", "temporario"), ("Eva Efetiva", "efetivo")):
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


# Sessão sempre no futuro, para os testes não dependerem da data em que rodam.
SESSAO = date.today() + timedelta(days=15)
SESSAO_ISO = f"{SESSAO.isoformat()}T09:30"
SESSAO_BR = f"{SESSAO:%d/%m/%Y} 09:30"

LICITACAO = {
    "numero_processo": "2026.000123",
    "numero_edital": "PE 010/2026",
    "modalidade": "Pregão Eletrônico",
    "objeto": "Aquisição de material de expediente",
    "data_sessao": SESSAO_ISO,
    "local": "Compras.gov.br",
    "valor_estimado": "150.000,50",
    "status": "Edital publicado",
    "data_publicacao": (date.today() - timedelta(days=10)).isoformat(),
    # Servidores 1, 2 e 5 são efetivos; 3 e 4 não.
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
         dict(LICITACAO, numero_processo="2026.999", modalidade="Leilão",
              numero_edital="LE 001/2026"),
         "/licitacoes/nova")

    html = client.get("/licitacoes?modalidade=Leilão").get_data(as_text=True)
    assert "2026.999" in html and "2026.000123" not in html

    ics = client.get("/licitacoes.ics").get_data(as_text=True)
    assert ics.count("BEGIN:VEVENT") == 2
    assert f"DTSTART:{SESSAO:%Y%m%d}T093000" in ics


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
    assert "Caio Comissionado, Dora Temporária não são efetivos" in html

    dados = dict(LICITACAO, membro1_id="1")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "mais de uma função" in html


def test_equipe_completa_exigida_fora_do_planejamento(client):
    entrar(client, "operador")
    dados = dict(LICITACAO, membro2_id="")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "Informe a equipe" in html

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


def gestor_registra_ferias(client, servidor_id, inicio, fim):
    url = f"/admin/servidores/{servidor_id}/afastamentos"
    return post(client, url, {"tipo": "Férias", "inicio": inicio.isoformat(),
                              "fim": fim.isoformat()}, url)


def abrir_sessao(client, id_):
    resp = post(client, f"/licitacoes/{id_}/editar", dict(LICITACAO, status="Em andamento"),
                f"/licitacoes/{id_}/editar")
    assert resp.status_code == 302


def test_numero_do_edital_obrigatorio_apos_planejamento(client):
    entrar(client, "operador")
    html = post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital=""),
                "/licitacoes/nova").get_data(as_text=True)
    assert "Informe o número do edital" in html


def test_painel_destaca_edital_cor_da_modalidade_e_equipe(client):
    entrar(client, "operador")
    criar_licitacao(client)
    html = client.get("/").get_data(as_text=True)
    assert '<a class="edital"' in html and "PE 010/2026" in html
    assert "--fundo: #e6f5ea" in html  # pregão eletrônico em verde
    assert "Pregoeiro(a):</span> Ana Efetiva" in html
    assert "Membros:</span> Beto Efetivo, Caio Comissionado" in html


def test_terceiro_membro_opcional(client):
    entrar(client, "operador")
    id_ = criar_licitacao(client)
    assert "Membro da equipe (3)" not in client.get(f"/licitacoes/{id_}").get_data(as_text=True)

    # Com 4 integrantes, 2 efetivos e 2 não efetivos não é minoria.
    dados = dict(LICITACAO, membro3_id="4")
    resp = post(client, f"/licitacoes/{id_}/editar", dados, f"/licitacoes/{id_}/editar")
    assert resp.status_code == 302
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Membro da equipe (3)" in pagina and "Dora Temporária" in pagina
    assert "Beto Efetivo, Caio Comissionado, Dora Temporária" in client.get("/").get_data(
        as_text=True)


def test_suspensao_e_remarcacao_antes_da_sessao(client):
    entrar(client, "operador")
    id_ = criar_licitacao(client)

    # Suspensão não é feita pelo formulário comum.
    html = post(client, f"/licitacoes/{id_}/editar", dict(LICITACAO, status="Suspensa"),
                f"/licitacoes/{id_}/editar").get_data(as_text=True)
    assert "Suspender / remarcar" in html

    url = f"/licitacoes/{id_}/suspender"
    tela = client.get(url).get_data(as_text=True)
    assert "Suspensa antes da abertura" in tela and "análise documental" not in tela
    # Antes da abertura não cabe suspensão para análise documental.
    html = post(client, url, {"tipo": "suspensa_analise", "suspensa_em": "2026-10-20T14:35"}, url)
    assert "Escolha o que aconteceu" in html.get_data(as_text=True)

    post(client, url, {"tipo": "suspensa_antes", "suspensa_em": "2026-10-20T14:35",
                       "motivo": "Impugnação do edital"}, url)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Suspensa — sessão não aberta" in pagina and "20/10/2026 14:35" in pagina
    assert "Suspensas" in client.get("/").get_data(as_text=True)

    html = post(client, url, {"tipo": "remarcada_antes", "nova_data": "2020-01-01T10:00"}, url)
    assert "deve ser futura" in html.get_data(as_text=True)
    post(client, url, {"tipo": "remarcada_retificacao", "nova_data": "2030-02-15T10:00",
                       "data_retificacao": "2026-10-21"}, url)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Remarcada — edital retificado" in pagina and "15/02/2030 10:00" in pagina
    assert "De 20/10/2026" not in pagina
    assert f"De {SESSAO_BR} para 15/02/2030 10:00. Edital retificado em 21/10/2026" in pagina


def test_suspensao_para_analise_e_continuacao_com_sessao_em_andamento(client):
    entrar(client, "operador")
    id_ = criar_licitacao(client)
    abrir_sessao(client, id_)

    url = f"/licitacoes/{id_}/suspender"
    tela = client.get(url).get_data(as_text=True)
    assert "Suspensa para análise documental" in tela and "Suspensa antes" not in tela

    post(client, url, {"tipo": "suspensa_analise", "suspensa_em": "2026-10-21T11:00",
                       "motivo": "Análise da habilitação"}, url)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Em andamento — suspensa p/ análise documental" in pagina
    painel = client.get("/").get_data(as_text=True)
    assert "Em andamento — suspensa p/ análise documental" in painel

    post(client, url, {"tipo": "continuacao", "nova_data": "2030-03-01T14:00"}, url)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Em andamento — continuação" in pagina and "01/03/2030 14:00" in pagina
    assert "Remarcada pelo pregoeiro (continuação)" in pagina


def test_consulta_nao_suspende(client):
    entrar(client, "gestor")
    id_ = criar_licitacao(client)
    client.post("/logout", data={"_csrf": csrf(client, "/")})
    entrar(client, "consulta")
    assert client.get(f"/licitacoes/{id_}/suspender").status_code == 403


def test_membro_de_ferias_antes_da_sessao_deve_ser_trocado(client):
    entrar(client, "gestor")
    gestor_registra_ferias(client, 2, SESSAO - timedelta(days=2), SESSAO + timedelta(days=5))
    html = post(client, "/licitacoes/nova", LICITACAO, "/licitacoes/nova").get_data(as_text=True)
    assert "Membro impedido na data da sessão" in html and "Beto Efetivo" in html
    assert "manter_impedidos" not in html  # antes da sessão não há opção de manter
    assert post(client, "/licitacoes/nova", dict(LICITACAO, membro1_id="5"),
                "/licitacoes/nova").status_code == 302


def test_membro_impedido_com_sessao_em_andamento_pode_ser_mantido(client):
    entrar(client, "gestor")
    id_ = criar_licitacao(client)
    abrir_sessao(client, id_)

    resp = gestor_registra_ferias(client, 2, SESSAO, SESSAO + timedelta(days=3))
    html = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "Atenção: Beto Efetivo está escalado(a)" in html and "PE 010/2026" in html
    painel = client.get("/").get_data(as_text=True)
    assert "Membro de equipe impedido" in painel and "Trocar ou manter o membro" in painel

    editar = f"/licitacoes/{id_}/editar"
    dados = dict(LICITACAO, status="Em andamento")
    html = post(client, editar, dados, editar).get_data(as_text=True)
    assert "troque o membro ou marque" in html and 'name="manter_impedidos"' in html

    assert post(client, editar, dict(dados, manter_impedidos="1"), editar).status_code == 302
    assert "Membro de equipe impedido" not in client.get("/").get_data(as_text=True)
    assert "Mantido membro impedido" in client.get(f"/licitacoes/{id_}").get_data(as_text=True)


def test_whatsapp_gera_imagem_de_celular(client):
    from PIL import Image

    entrar(client, "operador")
    id_ = criar_licitacao(client)
    post(client, "/licitacoes/nova", dict(LICITACAO, numero_processo="2026.HOMOLOG",
                                          status="Homologada"), "/licitacoes/nova")
    post(client, "/licitacoes/nova", dict(LICITACAO, numero_processo="2026.PLANEJ",
                                          status="Em planejamento"), "/licitacoes/nova")
    html = client.get("/licitacoes/whatsapp").get_data(as_text=True)
    assert "/licitacoes/whatsapp/1.png" in html and "/licitacoes/whatsapp/2.png" not in html
    assert "PE 010/2026" in html and f"Sessão: {SESSAO:%d/%m/%Y} às 09:30" in html
    assert "Pregoeiro(a): Ana Efetiva" in html and "Membros: Beto Efetivo, Caio Comissionado" in html
    assert "2026.HOMOLOG" not in html and "2026.PLANEJ" not in html

    resp = client.get("/licitacoes/whatsapp/1.png")
    assert resp.mimetype == "image/png"
    assert Image.open(io.BytesIO(resp.data)).size == (1080, 1920)
    assert client.get(f"/licitacoes/{id_}/whatsapp.png").mimetype == "image/png"

    for n in range(8):
        post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital=f"PE {n:03d}/2026"),
             "/licitacoes/nova")
    html = client.get("/licitacoes/whatsapp").get_data(as_text=True)
    assert "/licitacoes/whatsapp/2.png" in html
    assert client.get("/licitacoes/whatsapp/2.png").status_code == 200


def test_painel_mostra_sessoes_alem_de_30_dias(client):
    entrar(client, "operador")
    longe = (date.today() + timedelta(days=200)).isoformat() + "T09:00"
    post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital="PE 999/2027",
                                          data_sessao=longe), "/licitacoes/nova")
    assert "PE 999/2027" in client.get("/").get_data(as_text=True)


def test_banco_antigo_recebe_colunas_novas(tmp_path):
    import sqlite3
    caminho = tmp_path / "antigo.sqlite3"
    conn = sqlite3.connect(caminho)
    # Tabela como era na versão anterior, sem as colunas novas.
    conn.execute("CREATE TABLE licitacoes (id INTEGER PRIMARY KEY, numero_processo TEXT,"
                 " numero_edital TEXT, modalidade TEXT, objeto TEXT, data_publicacao TEXT,"
                 " data_sessao TEXT, vigencia_ate TEXT, local TEXT, agente_id INTEGER,"
                 " membro1_id INTEGER, membro2_id INTEGER, valor_estimado REAL, status TEXT,"
                 " suspensa_em TEXT, motivo_suspensao TEXT, observacoes TEXT, criado_por INTEGER,"
                 " criado_em TEXT, atualizado_em TEXT)")
    conn.commit()
    conn.close()
    create_app({"TESTING": True, "DATABASE": str(caminho)})
    colunas = {c[1] for c in sqlite3.connect(caminho).execute("PRAGMA table_info(licitacoes)")}
    assert {"membro3_id", "ocorrencia", "impedimentos_mantidos"} <= colunas
