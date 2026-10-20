"""Perfis de acesso, permissões e tabelas de domínio."""

PERFIS = {
    "administrador": "Administrador",
    "gestor": "Gestor",
    "operador": "Operador",
    "consulta": "Consulta",
}

DESCRICAO_PERFIS = {
    "administrador": "Acesso total, incluindo cadastro de usuários e auditoria.",
    "gestor": "Cadastra, edita e exclui licitações; consulta a auditoria.",
    "operador": "Cadastra e edita licitações (não exclui).",
    "consulta": "Apenas visualiza a agenda e as licitações.",
}

# Permissão -> perfis que a possuem.
PERMISSOES = {
    "ver": {"administrador", "gestor", "operador", "consulta"},
    "criar": {"administrador", "gestor", "operador"},
    "editar": {"administrador", "gestor", "operador"},
    "excluir": {"administrador", "gestor"},
    "auditoria": {"administrador", "gestor"},
    "usuarios": {"administrador"},
}

# Modalidades da Lei nº 14.133/2021 e contratações diretas.
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
]

# Situação -> classe CSS usada para colorir.
STATUS = {
    "Em planejamento": "cinza",
    "Edital publicado": "azul",
    "Em andamento": "amarelo",
    "Suspensa": "laranja",
    "Homologada": "verde",
    "Deserta": "vermelho",
    "Fracassada": "vermelho",
    "Revogada": "vermelho",
    "Anulada": "vermelho",
}

# Situações que ainda exigem acompanhamento na agenda.
STATUS_ABERTOS = ["Em planejamento", "Edital publicado", "Em andamento", "Suspensa"]


def tem_permissao(perfil, permissao):
    return perfil in PERMISSOES.get(permissao, set())
