"""Perfis de acesso, permissões e tabelas de domínio."""

PERFIS = {
    "administrador": "Administrador",
    "gestor": "Gestor",
    "operador": "Operador",
    "consulta": "Consulta",
}

DESCRICAO_PERFIS = {
    "administrador": "Acesso total, incluindo cadastro de usuários e auditoria.",
    "gestor": "Cadastra, edita e exclui licitações; mantém o cadastro de servidores; "
              "consulta a auditoria.",
    "operador": "Cadastra e edita licitações, registra suspensões e remarcações (não exclui).",
    "consulta": "Apenas visualiza a agenda e as licitações.",
}

# Permissão -> perfis que a possuem.
PERMISSOES = {
    "ver": {"administrador", "gestor", "operador", "consulta"},
    "criar": {"administrador", "gestor", "operador"},
    "editar": {"administrador", "gestor", "operador"},
    "suspender": {"administrador", "gestor", "operador"},  # suspender / remarcar sessão
    "excluir": {"administrador", "gestor"},
    "servidores": {"administrador", "gestor"},
    "auditoria": {"administrador", "gestor"},
    "usuarios": {"administrador"},
}

CREDENCIAMENTO = "Credenciamento"

# Modalidades da Lei nº 14.133/2021, contratações diretas e credenciamento.
MODALIDADES = [
    "Pregão Eletrônico",
    "Pregão Presencial",
    "Concorrência Eletrônica",
    "Concorrência Presencial",
    "Concurso",
    "Leilão",
    "Diálogo Competitivo",
    "Dispensa Eletrônica",
    "Inexigibilidade",
    CREDENCIAMENTO,
]

# Modalidade -> (fundo suave, cor de destaque), usadas nas linhas das tabelas e na imagem.
CORES_MODALIDADE = {
    "Pregão Eletrônico": ("#e6f5ea", "#1e7b3c"),
    "Pregão Presencial": ("#fbe7e7", "#b42318"),
    "Concorrência Eletrônica": ("#e5eefb", "#1d4f91"),
    "Concorrência Presencial": ("#fdefdd", "#b35a00"),
    "Concurso": ("#efe7fb", "#6a3fb5"),
    "Leilão": ("#fbf5d6", "#8a6d00"),
    "Diálogo Competitivo": ("#e1f4f4", "#0f7676"),
    "Dispensa Eletrônica": ("#f3ece3", "#7a5230"),
    "Inexigibilidade": ("#eceef1", "#4b5563"),
    CREDENCIAMENTO: ("#fbe8f2", "#a3266b"),
}

# Situação -> classe CSS usada para colorir.
STATUS = {
    "Em planejamento": "cinza",
    "Edital publicado": "azul",
    "Remarcada": "roxo",
    "Em andamento": "amarelo",
    "Suspensa": "laranja",
    "Homologada": "verde",
    "Concluída": "verde",
    "Deserta": "vermelho",
    "Fracassada": "vermelho",
    "Revogada": "vermelho",
    "Anulada": "vermelho",
}

# Situações que ainda exigem acompanhamento na agenda.
STATUS_ABERTOS = ["Em planejamento", "Edital publicado", "Remarcada", "Em andamento", "Suspensa"]

# Situações divulgadas ao público (exportação para WhatsApp).
STATUS_DIVULGAVEIS = ["Edital publicado", "Remarcada", "Em andamento", "Suspensa"]

# O credenciamento fica aberto indefinidamente, renovado a cada ano.
STATUS_CREDENCIAMENTO = ["Em andamento", "Concluída"]

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


def tem_permissao(perfil, permissao):
    return perfil in PERMISSOES.get(permissao, set())
