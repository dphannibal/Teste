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
}


def tem_permissao(perfil, permissao):
    return perfil in PERMISSOES.get(permissao, set())
