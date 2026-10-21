"""Regras de composição da equipe e impedimentos (férias, licenças, afastamentos)."""
from datetime import date

from .db import get_db
from .perfis import EQUIPE_OBRIGATORIA, FUNCOES_EQUIPE, VINCULOS_EFETIVOS

EQUIPE = list(FUNCOES_EQUIPE)


def servidores(incluir=()):
    """Servidores ativos, mais os já escalados (mesmo se inativos), com seus afastamentos
    futuros no formato 'inicio:fim:tipo;...' para o aviso imediato no formulário."""
    ids = [i for i in incluir if i] or [0]
    return get_db().execute(
        "SELECT s.*, (SELECT group_concat(a.inicio || ':' || a.fim || ':' || a.tipo, ';')"
        "               FROM afastamentos a"
        "              WHERE a.servidor_id = s.id AND a.fim >= date('now', 'localtime'))"
        "             AS afastamentos"
        f" FROM servidores s WHERE s.ativo = 1 OR s.id IN ({','.join('?' * len(ids))})"
        " ORDER BY s.nome",
        ids,
    ).fetchall()


def problemas(ids, lista_servidores):
    """Composição: sem repetição e sem minoria de efetivos."""
    por_id = {s["id"]: s for s in lista_servidores}
    escalados = [por_id[i] for i in ids if i in por_id]
    erros = []
    if len({s["id"] for s in escalados}) < len(escalados):
        erros.append("Um mesmo servidor foi escalado em mais de uma função na equipe.")
    nao_efetivos = [s for s in escalados if s["vinculo"] not in VINCULOS_EFETIVOS]
    # Os efetivos precisam ser maioria estrita (empate não basta: 2 de 4 é recusado).
    # Avalia sobre a equipe mínima de 3, mesmo quando ainda incompleta.
    tamanho = max(len(escalados), len(EQUIPE_OBRIGATORIA))
    if len(nao_efetivos) * 2 >= tamanho:
        nomes = ", ".join(s["nome"] for s in nao_efetivos)
        erros.append(
            f"A equipe precisa de maioria de servidores efetivos: {nomes} não são "
            f"efetivos. Ao menos {tamanho // 2 + 1} dos {tamanho} integrantes devem ser do "
            "quadro efetivo."
        )
    return erros


def impedimentos(ids, dia):
    """Afastamentos de integrantes da equipe que coincidem com o dia da sessão."""
    ids = [i for i in ids if i]
    if not ids or not dia:
        return []
    return get_db().execute(
        "SELECT a.*, s.nome FROM afastamentos a JOIN servidores s ON s.id = a.servidor_id"
        f" WHERE a.servidor_id IN ({','.join('?' * len(ids))}) AND ? BETWEEN a.inicio AND a.fim"
        " ORDER BY s.nome",
        (*ids, dia),
    ).fetchall()


def descrever(impedimento):
    inicio = date.fromisoformat(impedimento["inicio"]).strftime("%d/%m/%Y")
    fim = date.fromisoformat(impedimento["fim"]).strftime("%d/%m/%Y")
    return f"{impedimento['nome']} ({impedimento['tipo'].lower()} de {inicio} a {fim})"


def ler_mantidos(texto):
    return {int(i) for i in (texto or "").split(",") if i.isdigit()}


def verificar(ids, data_sessao, em_andamento, mantidos, manter):
    """Confere se alguém da equipe estará afastado no dia da sessão.

    Antes de a sessão abrir, o membro impedido precisa ser trocado. Com a sessão em
    andamento, avisa e permite manter o membro (``manter``), registrando a decisão.
    Retorna (erros, pendentes, mantidos atualizados).
    """
    dia = data_sessao[:10] if data_sessao else None
    if not dia or dia < date.today().isoformat():
        return [], [], mantidos
    pendentes = [i for i in impedimentos(ids, dia) if i["id"] not in mantidos]
    if not pendentes:
        return [], [], mantidos
    nomes = "; ".join(descrever(i) for i in pendentes)
    quando = date.fromisoformat(dia).strftime("%d/%m/%Y")
    if not em_andamento:
        return [f"Membro impedido na data da sessão ({quando}): {nomes}. Troque o membro "
                "da equipe."], [], mantidos
    if manter:
        return [], [], mantidos | {i["id"] for i in pendentes}
    return [f"Membro impedido na data da sessão ({quando}): {nomes}. Como a licitação está "
            "em andamento, troque o membro ou marque “Manter o membro impedido”."], \
        pendentes, mantidos
