"""Imagem no formato de tela de celular (1080 × 1920) para divulgar pelo WhatsApp."""
import functools
import io
import os
from datetime import date, datetime

from PIL import Image, ImageDraw, ImageFont

from . import parametros

LARGURA, ALTURA = 1080, 1920
MARGEM = 48
TOPO = 300
RODAPE = 96
ESPACO_ENTRE_CARTOES = 28
PADDING = 34
BARRA = 14
LARGURA_TEXTO = LARGURA - 2 * MARGEM - 2 * PADDING - BARRA

FUNDO = "#f3f5f8"
PRIMARIA = "#1d4f91"
TEXTO = "#1f2933"
SUTIL = "#5f6b7a"
ALERTA = "#b35a00"

PASTA_FONTES = os.path.join(os.path.dirname(__file__), "static", "fontes")


@functools.lru_cache(maxsize=None)
def _fonte(peso, tamanho):
    arquivo = {"normal": "Inter-Regular.otf", "semi": "Inter-SemiBold.otf",
               "negrito": "Inter-Bold.otf"}[peso]
    return ImageFont.truetype(os.path.join(PASTA_FONTES, arquivo), tamanho)


# Estilo de cada parte do cartão: (peso, tamanho, altura da linha, máximo de linhas).
ESTILOS = {
    "titulo": ("negrito", 66, 78, 1),
    "modalidade": ("semi", 34, 46, 1),
    "quando": ("semi", 36, 48, 2),
    "objeto": ("normal", 32, 42, 4),
    "equipe": ("normal", 30, 40, 2),
}
ESPACO_APOS = {"titulo": 2, "modalidade": 16, "quando": 14, "objeto": 16, "equipe": 0}

_medidor = ImageDraw.Draw(Image.new("RGB", (1, 1)))


def _quebrar(texto, fonte, largura, max_linhas):
    """Quebra o texto em linhas que cabem na largura, com reticências se exceder."""
    palavras, linhas, atual = texto.split(), [], ""
    for palavra in palavras:
        tentativa = f"{atual} {palavra}".strip()
        if _medidor.textlength(tentativa, font=fonte) <= largura:
            atual = tentativa
        else:
            if atual:
                linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        ultima = linhas[-1]
        while ultima and _medidor.textlength(ultima + "…", font=fonte) > largura:
            ultima = ultima[:-1]
        linhas[-1] = ultima.rstrip() + "…"
    return linhas or [""]


def _data_hora(valor):
    return datetime.fromisoformat(valor).strftime("%d/%m/%Y às %H:%M")


def conteudo(lic):
    """Dados de um cartão: edital, modalidade, data e hora, objeto e equipe."""
    fase = parametros.fase(lic["status"])
    alerta = True
    if parametros.eh_credenciamento(lic["modalidade"]):
        alerta = False
        quando = "Credenciamento aberto"
        if lic["vigencia_ate"]:
            quando += f" — vigente até {date.fromisoformat(lic['vigencia_ate']):%d/%m/%Y}"
    elif fase == "suspensa":
        quando = "SUSPENSA — sessão sem nova data"
        if lic["suspensa_em"]:
            quando += f" (desde {_data_hora(lic['suspensa_em'])})"
    elif fase == "andamento" and lic["suspensa_em"]:
        quando = f"EM ANDAMENTO — suspensa para análise documental desde " \
                 f"{_data_hora(lic['suspensa_em'])}"
    elif not lic["data_sessao"]:
        quando = "Sessão: data a definir"
    elif fase == "remarcada":
        quando = f"REMARCADA para {_data_hora(lic['data_sessao'])}"
        if lic["ocorrencia"] == "remarcada_retificacao":
            quando += " (edital retificado)"
    elif fase == "andamento" and lic["ocorrencia"] == "continuacao":
        quando = f"Continuação da sessão: {_data_hora(lic['data_sessao'])}"
    else:
        alerta = False
        quando = f"Sessão: {_data_hora(lic['data_sessao'])}"
        if fase == "andamento":
            quando += " (em andamento)"

    funcao = parametros.modalidade(lic["modalidade"])["rotulo_condutor"]
    linhas_equipe = []
    if lic["agente_nome"]:
        linhas_equipe.append(f"{funcao}: {lic['agente_nome']}")
    # O terceiro membro é raro: só aparece quando foi escalado.
    membros = [lic[c] for c in ("membro1_nome", "membro2_nome", "membro3_nome") if lic[c]]
    if membros:
        linhas_equipe.append("Membros: " + ", ".join(membros))
    if not linhas_equipe:
        linhas_equipe.append("Equipe: a definir")

    fundo, destaque = parametros.cores_modalidade(lic["modalidade"])
    return {
        "titulo": parametros.edital(lic),
        "modalidade": lic["modalidade"],
        "quando": quando,
        "alerta": alerta,
        "objeto": lic["objeto"],
        "equipe": linhas_equipe,
        "fundo": fundo,
        "destaque": destaque,
    }


def _linhas_do_cartao(bloco):
    """[(estilo, linhas)] na ordem de desenho."""
    partes = []
    for chave in ("titulo", "modalidade", "quando", "objeto"):
        peso, tamanho, _, maximo = ESTILOS[chave]
        texto = bloco[chave] if chave != "objeto" else f"Objeto: {bloco['objeto']}"
        partes.append((chave, _quebrar(texto, _fonte(peso, tamanho), LARGURA_TEXTO, maximo)))
    peso, tamanho, _, maximo = ESTILOS["equipe"]
    for linha in bloco["equipe"]:
        partes.append(("equipe", _quebrar(linha, _fonte(peso, tamanho), LARGURA_TEXTO, maximo)))
    return partes


def _altura(bloco):
    return 2 * PADDING + sum(ESTILOS[c][2] * len(l) + ESPACO_APOS[c]
                             for c, l in _linhas_do_cartao(bloco))


def paginar(blocos):
    """Distribui os cartões em quantas imagens forem necessárias."""
    disponivel = ALTURA - TOPO - RODAPE - 2 * ESPACO_ENTRE_CARTOES
    paginas, atual, usado = [], [], 0
    for bloco in blocos:
        altura = _altura(bloco)
        if atual and usado + altura > disponivel:
            paginas.append(atual)
            atual, usado = [], 0
        atual.append(bloco)
        usado += altura + ESPACO_ENTRE_CARTOES
    paginas.append(atual)
    return paginas


def desenhar(blocos, pagina, total, titulo, orgao):
    img = Image.new("RGB", (LARGURA, ALTURA), FUNDO)
    d = ImageDraw.Draw(img)

    d.rectangle((0, 0, LARGURA, TOPO - 40), fill=PRIMARIA)
    d.text((MARGEM, 58), titulo, font=_fonte("negrito", 72), fill="white")
    d.text((MARGEM, 152), orgao, font=_fonte("normal", 36), fill="#c8d6ea")
    d.text((MARGEM, 202), f"Atualizado em {datetime.now():%d/%m/%Y às %H:%M}",
           font=_fonte("semi", 30), fill="white")
    if total > 1:
        texto = f"{pagina}/{total}"
        fonte = _fonte("negrito", 40)
        d.text((LARGURA - MARGEM - d.textlength(texto, font=fonte), 66), texto, font=fonte,
               fill="white")

    y = TOPO
    if not blocos:
        texto = "Não há licitações abertas no momento."
        fonte = _fonte("semi", 40)
        d.text(((LARGURA - d.textlength(texto, font=fonte)) / 2, ALTURA / 2), texto,
               font=fonte, fill=SUTIL)
    for bloco in blocos:
        altura = _altura(bloco)
        d.rounded_rectangle((MARGEM, y, LARGURA - MARGEM, y + altura), radius=22,
                            fill=bloco["fundo"])
        d.rounded_rectangle((MARGEM, y, MARGEM + BARRA + 10, y + altura), radius=22,
                            fill=bloco["destaque"])
        d.rectangle((MARGEM + BARRA, y, MARGEM + BARRA + 12, y + altura), fill=bloco["fundo"])

        x, ty = MARGEM + BARRA + PADDING, y + PADDING
        for chave, linhas in _linhas_do_cartao(bloco):
            peso, tamanho, passo, _ = ESTILOS[chave]
            cor = {"titulo": bloco["destaque"], "modalidade": bloco["destaque"],
                   "quando": ALERTA if bloco["alerta"] else TEXTO,
                   "objeto": TEXTO, "equipe": "#344054"}[chave]
            for linha in linhas:
                d.text((x, ty), linha, font=_fonte(peso, tamanho), fill=cor)
                ty += passo
            ty += ESPACO_APOS[chave]
        y += altura + ESPACO_ENTRE_CARTOES

    rodape = f"Agenda de Licitações · {orgao}"
    if total > 1:
        rodape += f" · página {pagina} de {total}"
    fonte = _fonte("normal", 26)
    d.text(((LARGURA - d.textlength(rodape, font=fonte)) / 2, ALTURA - RODAPE + 30), rodape,
           font=fonte, fill=SUTIL)

    saida = io.BytesIO()
    img.save(saida, "PNG", optimize=True)
    return saida.getvalue()
