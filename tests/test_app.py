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
        for perfil in ("administrador", "gestor", "pregoeiro", "consulta"):
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
    "numero_edital": "010/2026",
    "modalidade": "Pregão Eletrônico",
    "objeto": "Aquisição de material de expediente",
    "data_sessao": SESSAO_ISO,
    "local": "Compras.gov.br",
    "valor_estimado": "150.000,50",
    "status": "publicado",
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


def test_pregoeiro_cria_e_edita_mas_nao_exclui(client):
    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)

    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "R$ 150.000,50" in pagina
    assert "Excluir" not in pagina

    dados = dict(LICITACAO, status="homologada")
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
    entrar(client, "pregoeiro")
    dados = dict(LICITACAO, modalidade="Inventada", valor_estimado="abc", objeto="")
    resp = post(client, "/licitacoes/nova", dados, "/licitacoes/nova")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "modalidade válida" in html and "Valor estimado inválido" in html


def test_filtros_e_exportacao_ics(client):
    entrar(client, "pregoeiro")
    criar_licitacao(client)
    post(client, "/licitacoes/nova",
         dict(LICITACAO, numero_processo="2026.999", modalidade="Leilão",
              numero_edital="001/2026"),
         "/licitacoes/nova")

    html = client.get("/licitacoes?modalidade=Leilão").get_data(as_text=True)
    assert "2026.999" in html and "2026.000123" not in html

    ics = client.get("/licitacoes.ics").get_data(as_text=True)
    assert ics.count("BEGIN:VEVENT") == 2
    assert f"DTSTART:{SESSAO:%Y%m%d}T093000" in ics


def test_admin_gerencia_usuarios(client, app):
    entrar(client, "administrador")
    resp = post(client, "/admin/usuarios/novo",
                {"nome": "Maria Silva", "login": "maria.silva", "perfil": "pregoeiro"},
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
    entrar(client, "pregoeiro")
    dados = dict(LICITACAO, membro1_id="3", membro2_id="4")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "maioria de servidores efetivos" in html
    assert "Caio Comissionado, Dora Temporária não são efetivos" in html

    dados = dict(LICITACAO, membro1_id="1")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "mais de uma função" in html


def test_equipe_completa_exigida_fora_do_planejamento(client):
    entrar(client, "pregoeiro")
    dados = dict(LICITACAO, membro2_id="")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "Informe a equipe" in html

    dados = dict(LICITACAO, membro2_id="", status="planejamento", data_sessao="")
    assert post(client, "/licitacoes/nova", dados, "/licitacoes/nova").status_code == 302


def test_credenciamento_aberto_e_renovado_anualmente(client):
    entrar(client, "gestor")
    dados = dict(LICITACAO, modalidade="Credenciamento", numero_edital="001/2026",
                 data_publicacao="2026-03-10", status="publicado")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "Credenciamento só pode estar em andamento" in html

    dados["status"] = "andamento"
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
    resp = post(client, f"/licitacoes/{id_}/editar", dict(LICITACAO, status="andamento"),
                f"/licitacoes/{id_}/editar")
    assert resp.status_code == 302


def test_numero_do_edital_obrigatorio_apos_planejamento(client):
    entrar(client, "pregoeiro")
    html = post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital=""),
                "/licitacoes/nova").get_data(as_text=True)
    assert "Informe o número do edital" in html


def test_painel_destaca_edital_cor_da_modalidade_e_equipe(client):
    entrar(client, "pregoeiro")
    criar_licitacao(client)
    html = client.get("/").get_data(as_text=True)
    assert '<a class="edital"' in html and "PE 010/2026" in html
    assert "--destaque: #1e7b3c" in html  # pregão eletrônico em verde
    assert "Pregoeiro(a):</span> Ana Efetiva" in html
    assert "Membros:</span> Beto Efetivo, Caio Comissionado" in html


def test_terceiro_membro_opcional(client):
    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)
    assert "Membro da equipe (3)" not in client.get(f"/licitacoes/{id_}").get_data(as_text=True)

    # Com 4 integrantes, 2 efetivos e 2 não efetivos é empate: não é maioria.
    editar = f"/licitacoes/{id_}/editar"
    html = post(client, editar, dict(LICITACAO, membro3_id="4"), editar).get_data(as_text=True)
    assert "Ao menos 3 dos 4 integrantes" in html

    resp = post(client, editar, dict(LICITACAO, membro3_id="5"), editar)
    assert resp.status_code == 302
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Membro da equipe (3)" in pagina and "Eva Efetiva" in pagina
    assert "Beto Efetivo, Caio Comissionado, Eva Efetiva" in client.get("/").get_data(
        as_text=True)


def test_suspensao_e_remarcacao_antes_da_sessao(client):
    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)

    # Suspensão não é feita pelo formulário comum.
    html = post(client, f"/licitacoes/{id_}/editar", dict(LICITACAO, status="suspensa"),
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
    entrar(client, "pregoeiro")
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
    # O aviso fica na licitação (e na edição), não no painel inicial.
    assert "Membro de equipe impedido" not in client.get("/").get_data(as_text=True)
    assert "Membro impedido na data da sessão" in client.get(f"/licitacoes/{id_}").get_data(
        as_text=True)

    editar = f"/licitacoes/{id_}/editar"
    dados = dict(LICITACAO, status="andamento")
    html = post(client, editar, dados, editar).get_data(as_text=True)
    assert "troque o membro ou marque" in html and 'name="manter_impedidos"' in html

    assert post(client, editar, dict(dados, manter_impedidos="1"), editar).status_code == 302
    assert "Membro impedido na data da sessão" not in client.get(f"/licitacoes/{id_}").get_data(
        as_text=True)
    assert "Mantido membro impedido" in client.get(f"/licitacoes/{id_}").get_data(as_text=True)


def test_whatsapp_gera_imagem_de_celular(client):
    from PIL import Image

    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)
    post(client, "/licitacoes/nova", dict(LICITACAO, numero_processo="2026.HOMOLOG",
                                          status="homologada"), "/licitacoes/nova")
    post(client, "/licitacoes/nova", dict(LICITACAO, numero_processo="2026.PLANEJ",
                                          status="planejamento"), "/licitacoes/nova")
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
        post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital=f"{n:03d}/2026"),
             "/licitacoes/nova")
    html = client.get("/licitacoes/whatsapp").get_data(as_text=True)
    assert "/licitacoes/whatsapp/2.png" in html
    assert client.get("/licitacoes/whatsapp/2.png").status_code == 200


def test_painel_mostra_sessoes_alem_de_30_dias(client):
    entrar(client, "pregoeiro")
    longe = (date.today() + timedelta(days=200)).isoformat() + "T09:00"
    post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital="999/2027",
                                          data_sessao=longe), "/licitacoes/nova")
    assert "PE 999/2027" in client.get("/").get_data(as_text=True)


def sair(client):
    client.post("/logout", data={"_csrf": csrf(client, "/")})


def test_edital_digitado_sem_sigla(client, app):
    entrar(client, "pregoeiro")
    # Se a sigla for digitada por engano, ela é retirada; a tela mostra sigla + número.
    id_ = int(post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital="pe 010/2026"),
                   "/licitacoes/nova").headers["Location"].rsplit("/", 1)[1])
    with app.app_context():
        assert get_db().execute("SELECT numero_edital FROM licitacoes WHERE id = ?",
                                (id_,)).fetchone()[0] == "010/2026"
    assert "PE 010/2026" in client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    html = post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital="ABC 1/2026"),
                "/licitacoes/nova").get_data(as_text=True)
    assert "sem a sigla" in html
    # A busca aceita sigla + número.
    assert "PE 010/2026" in client.get("/licitacoes?q=PE+010").get_data(as_text=True)
    assert "PE 010/2026" not in client.get("/licitacoes?q=PP+010").get_data(as_text=True)


def test_administrador_altera_permissoes_dos_perfis(client):
    entrar(client, "gestor")
    assert client.get("/admin/perfis").status_code == 403
    sair(client)

    entrar(client, "administrador")
    tela = client.get("/admin/perfis").get_data(as_text=True)
    assert "Pregoeiro / Agente de Contratação" in tela
    # Gestor perde "excluir"; pregoeiro ganha "afastamentos".
    gestor = ["ver", "criar", "editar", "suspender", "servidores", "afastamentos", "auditoria",
              "parametros"]
    post(client, "/admin/perfis", {"perm_gestor": gestor,
                                   "perm_pregoeiro": ["ver", "criar", "editar", "suspender",
                                                      "afastamentos"],
                                   "perm_consulta": ["ver"]}, "/admin/perfis")
    assert "Alteração de permissões" in client.get("/admin/auditoria").get_data(as_text=True)
    sair(client)

    entrar(client, "gestor")
    id_ = criar_licitacao(client)
    assert post(client, f"/licitacoes/{id_}/excluir", {}).status_code == 403
    sair(client)
    entrar(client, "pregoeiro")
    assert client.get("/admin/servidores/2/afastamentos").status_code == 200


def test_gestor_altera_parametros(client):
    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)
    assert client.get("/admin/parametros").status_code == 403
    sair(client)

    entrar(client, "gestor")
    assert client.get("/admin/parametros").status_code == 200
    post(client, "/admin/parametros/geral", {"nome_orgao": "Secretaria de Saúde"},
         "/admin/parametros")
    assert "Secretaria de Saúde" in client.get("/").get_data(as_text=True)

    # Modalidade: nova sigla, novo nome e nova cor valem para as licitações existentes.
    post(client, "/admin/modalidades/1/editar",
         {"nome": "Pregão Eletrônico SRP", "sigla": "pes", "cor": "#123456", "ordem": "0",
          "ativa": "1", "exige_equipe": "1", "rotulo_condutor": "Pregoeiro(a)"},
         "/admin/modalidades/1/editar")
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "PES 010/2026" in pagina and "Pregão Eletrônico SRP" in pagina
    assert "--destaque: #123456" in client.get("/").get_data(as_text=True)

    # Situação do sistema: renomeia, mas não exclui.
    post(client, "/admin/situacoes/publicado/editar",
         {"nome": "Aviso publicado", "cor": "#0000aa", "ordem": "1"},
         "/admin/situacoes/publicado/editar")
    assert "Aviso publicado" in client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    post(client, "/admin/situacoes/publicado/excluir", {})
    assert "Aviso publicado" in client.get("/admin/parametros").get_data(as_text=True)

    # Nova situação de encerramento, que depois pode ser excluída por não estar em uso.
    post(client, "/admin/situacoes/nova", {"nome": "Cancelada", "cor": "#990000",
                                           "fase": "encerrada", "ordem": "20", "ativa": "1"},
         "/admin/situacoes/nova")
    assert "Cancelada" in client.get("/licitacoes/nova").get_data(as_text=True)
    post(client, "/admin/situacoes/cancelada/excluir", {})
    assert "Cancelada" not in client.get("/admin/parametros").get_data(as_text=True)


def test_painel_licitacoes_em_andamento(client):
    entrar(client, "pregoeiro")
    publicada = criar_licitacao(client)
    aberta = criar_licitacao(client)
    abrir_sessao(client, aberta)
    url = f"/licitacoes/{aberta}/suspender"
    post(client, url, {"tipo": "suspensa_analise", "suspensa_em": "2026-10-21T11:00"}, url)
    antes = criar_licitacao(client)
    url = f"/licitacoes/{antes}/suspender"
    post(client, url, {"tipo": "suspensa_antes", "suspensa_em": "2026-10-21T11:00"}, url)

    html = client.get("/").get_data(as_text=True)
    em_andamento = html.split("Licitações em andamento")[1].split("Suspensas antes")[0]
    assert "suspensa p/ análise documental" in em_andamento
    assert "Edital publicado" in em_andamento
    assert "sessão não aberta" not in em_andamento
    assert "sessão não aberta" in html.split("Suspensas antes")[1]
    assert publicada


def test_ordenacao_e_colunas_do_painel(client):
    entrar(client, "pregoeiro")
    for numero in ("002/2026", "010/2025", "001/2026"):
        post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital=numero),
             "/licitacoes/nova")

    html = client.get("/?ordem=edital&dir=desc").get_data(as_text=True)
    assert html.index("PE 002/2026") < html.index("PE 001/2026") < html.index("PE 010/2025")
    # A escolha fica guardada para as próximas visitas.
    html = client.get("/").get_data(as_text=True)
    assert html.index("PE 002/2026") < html.index("PE 001/2026")

    post(client, "/preferencias/tabela",
         {"coluna": ["situacao", "edital", "objeto", "data"],
          "visivel": ["situacao", "edital", "data"], "ordem": "edital", "direcao": "asc",
          "voltar": "/"}, "/")
    html = client.get("/").get_data(as_text=True)
    tabela = html.split("Licitações em andamento")[1]
    assert tabela.index(">Situação") < tabela.index(">Edital") < tabela.index(">Data e hora")
    assert ">Objeto" not in tabela.split("</thead>")[0]
    assert html.index("PE 010/2025") < html.index("PE 001/2026") < html.index("PE 002/2026")


def test_banco_antigo_e_convertido(tmp_path):
    import sqlite3
    caminho = tmp_path / "antigo.sqlite3"
    conn = sqlite3.connect(caminho)
    conn.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, nome TEXT, login TEXT,"
                 " email TEXT, senha_hash TEXT, perfil TEXT, ativo INTEGER, trocar_senha INTEGER,"
                 " criado_em TEXT)")
    conn.execute("INSERT INTO usuarios (nome, login, senha_hash, perfil, ativo, trocar_senha)"
                 " VALUES ('Op', 'op', 'x', 'operador', 1, 0)")
    # Tabela como era na versão anterior, sem as colunas novas.
    conn.execute("CREATE TABLE licitacoes (id INTEGER PRIMARY KEY, numero_processo TEXT,"
                 " numero_edital TEXT, modalidade TEXT, objeto TEXT, data_publicacao TEXT,"
                 " data_sessao TEXT, vigencia_ate TEXT, local TEXT, agente_id INTEGER,"
                 " membro1_id INTEGER, membro2_id INTEGER, valor_estimado REAL, status TEXT,"
                 " suspensa_em TEXT, motivo_suspensao TEXT, observacoes TEXT, criado_por INTEGER,"
                 " criado_em TEXT, atualizado_em TEXT)")
    conn.execute("INSERT INTO licitacoes (numero_processo, numero_edital, modalidade, objeto,"
                 " status) VALUES ('1', 'PE 012/2026', 'Pregão Eletrônico', 'x', 'Em andamento')")
    conn.commit()
    conn.close()
    create_app({"TESTING": True, "DATABASE": str(caminho)})
    conn = sqlite3.connect(caminho)
    colunas = {c[1] for c in conn.execute("PRAGMA table_info(licitacoes)")}
    assert {"membro3_id", "ocorrencia", "impedimentos_mantidos"} <= colunas
    assert conn.execute("SELECT numero_edital, status FROM licitacoes").fetchone() == (
        "012/2026", "andamento")
    assert conn.execute("SELECT perfil FROM usuarios").fetchone()[0] == "pregoeiro"
