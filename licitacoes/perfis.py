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
    "excluir": "Excluir licitações",
    "servidores": "Cadastrar servidores",
    "afastamentos": "Registrar férias e afastamentos",
    "auditoria": "Consultar a auditoria",
    "parametros": "Alterar parâmetros: nome do órgão, modalidades, siglas, cores e situações",
    "usuarios": "Gerenciar usuários",
}

# O administrador sempre tem todas as permissões (evita perder o acesso ao sistema),
# e só ele altera as permissões dos perfis.
PERFIL_TOTAL = "administrador"

PERMISSOES_PADRAO = {
    "gestor": {"ver", "criar", "editar", "suspender", "excluir", "servidores", "afastamentos",
               "auditoria", "parametros"},
    "pregoeiro": {"ver", "criar", "editar", "suspender"},
    "consulta": {"ver"},
}

# (nome, sigla, cor, aberta com vigência anual, exige equipe, quem conduz)
MODALIDADES_PADRAO = [
    ("Pregão Eletrônico", "PE", "#1e7b3c", 0, 1, "Pregoeiro(a)"),
    ("Pregão Presencial", "PP", "#b42318", 0, 1, "Pregoeiro(a)"),
    ("Concorrência Eletrônica", "CE", "#1d4f91", 0, 1, "Agente de contratação"),
    ("Concorrência Presencial", "CP", "#b35a00", 0, 1, "Agente de contratação"),
    ("Concurso", "CS", "#6a3fb5", 0, 1, "Agente de contratação"),
    ("Leilão", "LE", "#8a6d00", 0, 1, "Agente de contratação"),
    ("Diálogo Competitivo", "DC", "#0f7676", 0, 1, "Agente de contratação"),
    ("Dispensa Eletrônica", "DE", "#7a5230", 0, 1, "Agente de contratação"),
    ("Inexigibilidade", "IN", "#4b5563", 0, 0, "Agente de contratação"),
    ("Credenciamento", "CR", "#a3266b", 1, 1, "Agente de contratação"),
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
