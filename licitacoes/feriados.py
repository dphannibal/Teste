"""Feriados, pontos facultativos, dias úteis e prazo mínimo legal (art. 55 da Lei 14.133)."""
from datetime import date, timedelta

from flask import g

from .db import get_db

NOMES_DIA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
             "sábado", "domingo"]

TIPOS = {"feriado": "Feriado", "ponto_facultativo": "Ponto facultativo"}
ABRANGENCIAS = {"nacional": "Nacional", "estadual": "Estadual (RJ)",
                "municipal": "Municipal (Três Rios)"}
REGRAS = {"fixa": "Todo ano na mesma data", "pascoa": "Móvel (calculado pela Páscoa)",
          "data": "Somente numa data específica"}


def pascoa(ano):
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g_ = (b - f + 1) // 3
    h = (19 * a + b - d - g_ + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mes = (h + l_ - 7 * m + 114) // 31
    dia = (h + l_ - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


def data_original(feriado, ano):
    """Data em que o feriado cai no ano, antes de eventual transferência."""
    try:
        if feriado["regra"] == "fixa":
            return date(ano, feriado["mes"], feriado["dia"])
        if feriado["regra"] == "pascoa":
            return pascoa(ano) + timedelta(days=feriado["deslocamento"] or 0)
        if feriado["regra"] == "data" and feriado["data"]:
            unica = date.fromisoformat(feriado["data"])
            return unica if unica.year == ano else None
    except (TypeError, ValueError):
        return None
    return None


def ocorrencias(ano):
    """{data: [ocorrências]} dos feriados e pontos facultativos ativos no ano, já com as
    transferências aplicadas (ex.: feriado municipal antecipado por decreto)."""
    cache = g.setdefault("feriados_por_ano", {})
    if ano not in cache:
        conn = get_db()
        transferencias = {
            t["feriado_id"]: t for t in conn.execute(
                "SELECT * FROM feriado_transferencias WHERE ano = ?", (ano,))
        }
        dias = {}
        for f in conn.execute("SELECT * FROM feriados WHERE ativo = 1"):
            original = data_original(f, ano)
            if original is None:
                continue
            transf = transferencias.get(f["id"])
            efetiva = date.fromisoformat(transf["nova_data"]) if transf else original
            dias.setdefault(efetiva, []).append({
                "id": f["id"], "nome": f["nome"], "tipo": f["tipo"],
                "abrangencia": f["abrangencia"],
                "transferido_de": original if transf else None,
                "ato": transf["ato"] if transf else None,
            })
        cache[ano] = dias
    return cache[ano]


def invalidar():
    g.pop("feriados_por_ano", None)


def motivos(dia):
    """Por que o dia não é útil: fim de semana, feriado ou ponto facultativo."""
    lista = []
    if dia.weekday() >= 5:
        lista.append({"nome": NOMES_DIA[dia.weekday()].capitalize(), "tipo": "fim_de_semana"})
    # Transferências podem levar um feriado para o ano vizinho.
    for ano in {dia.year, dia.year - 1, dia.year + 1}:
        lista += ocorrencias(ano).get(dia, [])
    return lista


def eh_dia_util(dia):
    """Dia com expediente: não é fim de semana, feriado nem ponto facultativo."""
    return not motivos(dia)


def descrever(motivo):
    if motivo["tipo"] == "fim_de_semana":
        return motivo["nome"]
    texto = f"{TIPOS[motivo['tipo']]} {ABRANGENCIAS[motivo['abrangencia']].split(' ')[0].lower()}"
    texto += f": {motivo['nome']}"
    if motivo.get("transferido_de"):
        texto += f" (transferido de {motivo['transferido_de']:%d/%m})"
    return texto


def criticar_data(dia):
    """(erros, avisos) para marcar sessão no dia: fim de semana e feriado impedem; ponto
    facultativo exige confirmação."""
    erros, avisos = [], []
    for m in motivos(dia):
        if m["tipo"] == "fim_de_semana":
            erros.append(f"{dia:%d/%m/%Y} cai num {m['nome'].lower()}.")
        else:
            texto = f"{dia:%d/%m/%Y} é {descrever(m)}."
            (avisos if m["tipo"] == "ponto_facultativo" else erros).append(texto)
    return erros, avisos


def dias_nao_uteis(inicio, fim):
    """Datas ISO não úteis entre inicio e fim (para o aviso imediato no formulário)."""
    dias, dia = {}, inicio
    while dia <= fim:
        lista = motivos(dia)
        if lista:
            dias[dia.isoformat()] = "; ".join(descrever(m) for m in lista)
        dia += timedelta(days=1)
    return dias


def proximo_dia_util(dia):
    while not eh_dia_util(dia):
        dia += timedelta(days=1)
    return dia


def contar_dias_uteis(inicio, dias_uteis, conta_o_inicio=False):
    """Último dia de um prazo de ``dias_uteis`` dias úteis.

    Regra geral (art. 183): exclui-se o dia do começo e conta-se a partir do dia útil
    seguinte. Com ``conta_o_inicio`` (aviso de dispensa eletrônica), o próprio dia entra na
    contagem se for útil."""
    dia, contados = inicio, 0
    if conta_o_inicio and eh_dia_util(dia):
        contados = 1
    while contados < dias_uteis:
        dia += timedelta(days=1)
        if eh_dia_util(dia):
            contados += 1
    return dia


def data_minima_sessao(divulgacao, dias_uteis, conta_divulgacao=False):
    """Primeira data possível para a sessão: o último dia do prazo mínimo (a sessão pode
    ser marcada para o mesmo dia em que o prazo termina)."""
    if not dias_uteis:
        return None
    return contar_dias_uteis(divulgacao, dias_uteis, conta_divulgacao)
