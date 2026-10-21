"""Perfis, permissões e valores padrão dos parâmetros.

Modalidades, situações, permissões por perfil e nome do órgão ficam no banco e são
alterados pelas telas de configuração; aqui estão apenas os valores iniciais.
"""

PERFIS = {
    "administrador": "Administrador",
    "gestor": "Gestor",
    "pregoeiro": "Pregoeiro / Agente de Contratação",
    "consulta": "Consulta",
}

# Permissão -> descrição exibida na tela de perfis.
PERMISSOES = {
    "ver": "Ver painel, calendário e licitações",
    "criar": "Cadastrar licitações",
    "editar": "Editar licitações e renovar credenciamentos",
    "suspender": "Suspender e remarcar sessões",
    "recursos": "Registrar recursos e suas decisões",
    "excluir": "Excluir licitações",
    "servidores": "Cadastrar servidores",
    "afastamentos": "Registrar férias e afastamentos",
    "feriados": "Cadastrar feriados, pontos facultativos e transferências",
    "auditoria": "Consultar a auditoria",
    "parametros": "Alterar parâmetros: nome do órgão, modalidades, siglas, cores e situações",
    "usuarios": "Gerenciar usuários",
}

# O administrador sempre tem todas as permissões (evita perder o acesso ao sistema),
# e só ele altera as permissões dos perfis.
PERFIL_TOTAL = "administrador"

PERMISSOES_PADRAO = {
    "gestor": {"ver", "criar", "editar", "suspender", "recursos", "excluir", "servidores",
               "afastamentos",
               "feriados", "auditoria", "parametros"},
    "pregoeiro": {"ver", "criar", "editar", "suspender", "recursos"},
    "consulta": {"ver"},
}

# Objeto e critério de julgamento -> (descrição, prazo mínimo em dias úteis entre a
# divulgação e a sessão, se a contagem inclui o próprio dia da divulgação).
# Art. 55 da Lei 14.133/2021; dispensa: art. 75, § 3º; diálogo competitivo: art. 32, § 1º, I.
PRAZOS = {
    "bens_menor_preco": ("Bens — menor preço ou maior desconto (art. 55, I, a)", 8, False),
    "bens_demais": ("Bens — demais critérios (art. 55, I, b)", 15, False),
    "servicos_comuns": ("Serviços comuns, obras e serviços comuns de engenharia — menor preço "
                        "ou maior desconto (art. 55, II, a)", 10, False),
    "servicos_especiais": ("Serviços especiais, obras e serviços especiais de engenharia — "
                           "menor preço ou maior desconto (art. 55, II, b)", 25, False),
    "integrada": ("Obras e serviços — contratação integrada (art. 55, II, c)", 60, False),
    "semi_integrada": ("Obras e serviços — contratação semi-integrada ou demais hipóteses "
                       "(art. 55, II, d)", 35, False),
    "maior_lance": ("Maior lance (art. 55, III)", 15, False),
    "tecnica": ("Técnica e preço, melhor técnica ou conteúdo artístico (art. 55, IV)", 35,
                False),
    # A dispensa eletrônica conta o próprio dia em que o aviso é publicado.
    "dispensa": ("Aviso de dispensa eletrônica (art. 75, § 3º) — conta o dia da publicação",
                 3, True),
    "dialogo": ("Manifestação de interesse no diálogo competitivo (art. 32, § 1º, I)", 25,
                False),
    "nao_se_aplica": ("Sem prazo mínimo", 0, False),
}

PREGAO = "bens_menor_preco,servicos_comuns"
CONCORRENCIA = ("bens_menor_preco,bens_demais,servicos_comuns,servicos_especiais,integrada,"
                "semi_integrada,tecnica")

# (nome, sigla, cor, aberta com vigência anual, exige equipe, quem conduz, objeto/critério
#  padrão, objetos/critérios cabíveis na modalidade)
MODALIDADES_PADRAO = [
    ("Pregão Eletrônico", "PE", "#1e7b3c", 0, 1, "Pregoeiro(a)", "bens_menor_preco", PREGAO),
    ("Pregão Presencial", "PP", "#b42318", 0, 1, "Pregoeiro(a)", "bens_menor_preco", PREGAO),
    ("Concorrência Eletrônica", "CE", "#1d4f91", 0, 1, "Agente de contratação",
     "servicos_comuns", CONCORRENCIA),
    ("Concorrência Presencial", "CP", "#b35a00", 0, 1, "Agente de contratação",
     "servicos_comuns", CONCORRENCIA),
    ("Concurso", "CS", "#6a3fb5", 0, 1, "Agente de contratação", "tecnica", "tecnica"),
    ("Leilão", "LE", "#8a6d00", 0, 1, "Agente de contratação", "maior_lance", "maior_lance"),
    ("Diálogo Competitivo", "DC", "#0f7676", 0, 1, "Agente de contratação", "dialogo",
     "dialogo"),
    ("Dispensa Eletrônica", "DE", "#7a5230", 0, 1, "Agente de contratação", "dispensa",
     "dispensa"),
    ("Inexigibilidade", "IN", "#4b5563", 0, 0, "Agente de contratação", "nao_se_aplica",
     "nao_se_aplica"),
    ("Credenciamento", "CR", "#a3266b", 1, 1, "Agente de contratação", "nao_se_aplica",
     "nao_se_aplica"),
]

# Prazos recursais (art. 165 da Lei 14.133/2021), em dias úteis.
PRAZO_RAZOES = 3            # razões, contados da intimação ou da lavratura da ata (I)
PRAZO_CONTRARRAZOES = 3     # contrarrazões, contadas do fim do prazo das razões (§ 4º)
PRAZO_RECONSIDERACAO = 3    # reconsideração pela autoridade que praticou o ato (§ 2º)
PRAZO_DECISAO = 10          # decisão da autoridade superior (§ 2º)

# (nome, tipo, abrangência, regra, dia, mês, deslocamento da Páscoa, observação)
FERIADOS_PADRAO = [
    ("Confraternização Universal", "feriado", "nacional", "fixa", 1, 1, None, "Lei 662/1949"),
    ("Carnaval (segunda-feira)", "ponto_facultativo", "nacional", "pascoa", None, None, -48,
     "Ponto facultativo federal"),
    ("Carnaval (terça-feira)", "feriado", "nacional", "pascoa", None, None, -47,
     "Considerado feriado na secretaria"),
    ("Quarta-feira de Cinzas", "ponto_facultativo", "nacional", "pascoa", None, None, -46,
     "Ponto facultativo até as 14h"),
    ("Paixão de Cristo (Sexta-feira Santa)", "feriado", "nacional", "pascoa", None, None, -2,
     "Lei 9.093/1995"),
    ("Tiradentes", "feriado", "nacional", "fixa", 21, 4, None, "Lei 662/1949"),
    ("São Jorge", "feriado", "estadual", "fixa", 23, 4, None, "Lei estadual 5.198/2008"),
    ("Dia do Trabalho", "feriado", "nacional", "fixa", 1, 5, None, "Lei 662/1949"),
    ("Corpus Christi", "ponto_facultativo", "nacional", "pascoa", None, None, 60,
     "Ponto facultativo federal"),
    ("Independência do Brasil", "feriado", "nacional", "fixa", 7, 9, None, "Lei 662/1949"),
    ("Nossa Senhora Aparecida", "feriado", "nacional", "fixa", 12, 10, None, "Lei 6.802/1980"),
    ("Dia do Servidor Público", "feriado", "nacional", "fixa", 28, 10, None,
     "Considerado feriado na secretaria; costuma ser transferido por decreto"),
    ("Finados", "feriado", "nacional", "fixa", 2, 11, None, "Lei 662/1949"),
    ("Proclamação da República", "feriado", "nacional", "fixa", 15, 11, None, "Lei 662/1949"),
    ("Dia Nacional de Zumbi e da Consciência Negra", "feriado", "nacional", "fixa", 20, 11,
     None, "Lei 14.759/2023 (no RJ, feriado estadual desde a Lei 4.007/2002)"),
    ("Natal", "feriado", "nacional", "fixa", 25, 12, None, "Lei 662/1949"),
    ("São Sebastião, padroeiro de Três Rios", "feriado", "municipal", "fixa", 20, 1, None,
     "Feriado municipal de Três Rios"),
    ("Emancipação de Três Rios", "feriado", "municipal", "fixa", 14, 12, None,
     "Feriado municipal de Três Rios; normalmente transferido — registre a transferência "
     "a cada ano"),
]

# Fase -> descrição. O comportamento do sistema depende da fase, não do nome da situação.
FASES = {
    "planejamento": "Em planejamento (edital ainda não publicado)",
    "publicada": "Edital publicado, sessão ainda não aberta",
    "remarcada": "Sessão remarcada antes da abertura",
    "suspensa": "Suspensa antes da abertura da sessão",
    "andamento": "Em andamento (sessão aberta)",
    "concluida": "Concluída com sucesso",
    "encerrada": "Encerrada sem sucesso (deserta, fracassada, revogada…)",
}

# (chave, nome, cor, fase, situação do sistema)
# As do sistema são usadas pelas ações (suspender, remarcar…): podem ser renomeadas e
# recoloridas, mas não excluídas nem mudar de fase.
SITUACOES_PADRAO = [
    ("planejamento", "Em planejamento", "#475467", "planejamento", 1),
    ("publicado", "Edital publicado", "#1d4f91", "publicada", 1),
    ("remarcada", "Remarcada", "#5b2ca0", "remarcada", 1),
    ("andamento", "Em andamento", "#7a5a00", "andamento", 1),
    ("recurso", "Em recurso", "#c2410c", "andamento", 1),
    ("suspensa", "Suspensa", "#9a3d00", "suspensa", 1),
    ("homologada", "Homologada", "#146c2e", "concluida", 0),
    ("concluida", "Concluída", "#146c2e", "concluida", 1),
    ("deserta", "Deserta", "#9b1c13", "encerrada", 0),
    ("fracassada", "Fracassada", "#9b1c13", "encerrada", 0),
    ("revogada", "Revogada", "#9b1c13", "encerrada", 0),
    ("anulada", "Anulada", "#9b1c13", "encerrada", 0),
]

FASES_ABERTAS = ("planejamento", "publicada", "remarcada", "suspensa", "andamento")
FASES_ANTES_DA_SESSAO = ("publicada", "remarcada", "suspensa")
# Painel "Licitações em andamento": publicadas, remarcadas e com sessão aberta
# (inclusive as suspensas depois de abertas, para análise documental).
FASES_EM_ANDAMENTO = ("publicada", "remarcada", "andamento")
FASES_DIVULGAVEIS = ("publicada", "remarcada", "suspensa", "andamento")
FASES_CREDENCIAMENTO = ("andamento", "concluida")
# Fases só alcançadas pela ação "Suspender / remarcar".
FASES_DA_ACAO = ("suspensa", "remarcada")

# Vínculo funcional do servidor. Os do quadro permanente contam como "efetivos"
# na composição da equipe (art. 8º da Lei nº 14.133/2021).
VINCULOS = {
    "efetivo": "Efetivo",
    "empregado": "Empregado público (quadro permanente)",
    "comissionado": "Comissionado",
    "temporario": "Temporário / contratado",
}
VINCULOS_EFETIVOS = {"efetivo", "empregado"}

FUNCOES_EQUIPE = {
    "agente_id": "Pregoeiro / agente de contratação",
    "membro1_id": "Membro da equipe (1)",
    "membro2_id": "Membro da equipe (2)",
    "membro3_id": "Membro da equipe (3, opcional)",
}
EQUIPE_OBRIGATORIA = ["agente_id", "membro1_id", "membro2_id"]

TIPOS_AFASTAMENTO = ["Férias", "Licença", "Afastamento", "Outro"]

# Ocorrências da sessão pública. "fase" indica se a sessão já foi aberta;
# "campo" é a data e hora exigida (quando ocorreu ou a nova data da sessão).
OCORRENCIAS = {
    "suspensa_antes": {
        "rotulo": "Suspensa antes da abertura da sessão",
        "descricao": "A sessão pública ainda não foi aberta e fica sem data definida.",
        "fase": "antes", "campo": "suspensa_em",
    },
    "remarcada_antes": {
        "rotulo": "Remarcada antes da sessão",
        "descricao": "A sessão ainda não foi aberta e passa para uma nova data.",
        "fase": "antes", "campo": "nova_data",
    },
    "remarcada_retificacao": {
        "rotulo": "Remarcada após retificação do edital",
        "descricao": "O edital foi retificado e republicado, com nova data de sessão.",
        "fase": "antes", "campo": "nova_data",
    },
    "suspensa_analise": {
        "rotulo": "Suspensa para análise documental",
        "descricao": "A sessão já foi aberta; o pregoeiro a suspende para analisar "
                     "documentos e a licitação segue em andamento.",
        "fase": "andamento", "campo": "suspensa_em",
    },
    "continuacao": {
        "rotulo": "Remarcada pelo pregoeiro (continuação)",
        "descricao": "A sessão já foi aberta e não terminou no mesmo dia; continua em "
                     "nova data.",
        "fase": "andamento", "campo": "nova_data",
    },
}

# Colunas das tabelas de licitações (ordem e visibilidade escolhidas por usuário).
COLUNAS = {
    "edital": "Edital",
    "data": "Data e hora",
    "modalidade": "Modalidade",
    "objeto": "Objeto",
    "equipe": "Equipe",
    "situacao": "Situação",
    "local": "Local / plataforma",
    "valor": "Valor estimado",
    "publicacao": "Publicação",
}
COLUNAS_PADRAO = ["edital", "data", "modalidade", "objeto", "equipe", "situacao"]
