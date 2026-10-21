"""Imagem no formato de tela de celular (1080 × 1920) para divulgar pelo WhatsApp."""
import functools
import io
import os
from datetime import date, datetime

from PIL import Image, ImageDraw, ImageFont

from . import brasao, parametros

LARGURA, ALTURA = 1080, 1920
MARGEM = 48
RODAPE = 80
BARRA = 14

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


# Layouts do mais confortável ao mais compacto. Escolhe-se o primeiro em que todas as
# licitações cabem numa imagem; se nem o compacto basta, ele é usado em várias imagens.
# A legibilidade é preservada: nenhum texto fica abaixo de 26 px numa imagem de 1080 px
# de largura (o tamanho de leitura de uma legenda na tela do celular).
# Estilos: (peso, tamanho, altura da linha, máximo de linhas).
LAYOUTS = [
    {
        "nome": "grande", "padding": 34, "espaco": 28,
        "cabecalho": (72, 36, 30), "modalidade_ao_lado": False, "equipe_unida": False,
        "estilos": {"titulo": ("negrito", 66, 78, 1), "modalidade": ("semi", 34, 46, 1),
                    "quando": ("semi", 36, 48, 2), "objeto": ("normal", 32, 42, 4),
                    "equipe": ("normal", 30, 40, 2)},
        "espaco_apos": {"titulo": 2, "modalidade": 16, "quando": 14, "objeto": 16, "equipe": 0},
    },
    {
        "nome": "medio", "padding": 26, "espaco": 20,
        "cabecalho": (60, 32, 27), "modalidade_ao_lado": True, "equipe_unida": False,
        "estilos": {"titulo": ("negrito", 54, 64, 1), "modalidade": ("semi", 30, 64, 1),
                    "quando": ("semi", 31, 40, 2), "objeto": ("normal", 28, 36, 3),
                    "equipe": ("normal", 27, 35, 2)},
        "espaco_apos": {"titulo": 6, "modalidade": 6, "quando": 8, "objeto": 10, "equipe": 0},
    },
    {
        "nome": "compacto", "padding": 20, "espaco": 14,
        "cabecalho": (54, 30, 26), "modalidade_ao_lado": True, "equipe_unida": True,
        "estilos": {"titulo": ("negrito", 46, 54, 1), "modalidade": ("semi", 26, 54, 1),
                    "quando": ("semi", 28, 35, 2), "objeto": ("normal", 26, 33, 2),
                    "equipe": ("normal", 26, 33, 2)},
        "espaco_apos": {"titulo": 4, "modalidade": 4, "quando": 6, "objeto": 6, "equipe": 0},
    },
    {
        # Mesmo tamanho mínimo de letra do compacto, com menos espaço entre as linhas.
        "nome": "denso", "padding": 16, "espaco": 10,
        "cabecalho": (48, 26, 26), "modalidade_ao_lado": True, "equipe_unida": True,
        "estilos": {"titulo": ("negrito", 40, 46, 1), "modalidade": ("semi", 26, 46, 1),
                    "quando": ("semi", 26, 31, 2), "objeto": ("normal", 26, 31, 2),
                    "equipe": ("normal", 26, 31, 2)},
        "espaco_apos": {"titulo": 2, "modalidade": 2, "quando": 3, "objeto": 3, "equipe": 0},
    },
]

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
    elif lic["recurso_id"]:
        quando = (f"EM RECURSO — razões até {date.fromisoformat(lic['razoes_ate']):%d/%m/%Y}; "
                  f"contrarrazões até {date.fromisoformat(lic['contrarrazoes_ate']):%d/%m/%Y}")
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


def _largura_texto(layout):
    return LARGURA - 2 * MARGEM - 2 * layout["padding"] - BARRA


def _modalidade_ao_lado(bloco, layout):
    """No layout compacto a modalidade vai à direita do edital, se couber na linha."""
    if not layout["modalidade_ao_lado"]:
        return False
    est = layout["estilos"]
    largura = (_medidor.textlength(bloco["titulo"], font=_fonte(*est["titulo"][:2]))
               + _medidor.textlength(bloco["modalidade"], font=_fonte(*est["modalidade"][:2])))
    return largura + 24 <= _largura_texto(layout)


def _linhas_do_cartao(bloco, layout):
    """[(estilo, linhas)] na ordem de desenho."""
    est, largura = layout["estilos"], _largura_texto(layout)
    partes = []

    def adicionar(chave, texto):
        peso, tamanho, _, maximo = est[chave]
        partes.append((chave, _quebrar(texto, _fonte(peso, tamanho), largura, maximo)))

    adicionar("titulo", bloco["titulo"])
    if not _modalidade_ao_lado(bloco, layout):
        adicionar("modalidade", bloco["modalidade"])
    adicionar("quando", bloco["quando"])
    adicionar("objeto", f"Objeto: {bloco['objeto']}")
    if layout["equipe_unida"]:
        adicionar("equipe", " · ".join(bloco["equipe"]))
    else:
        for linha in bloco["equipe"]:
            adicionar("equipe", linha)
    return partes


def _altura(bloco, layout):
    return 2 * layout["padding"] + sum(
        layout["estilos"][c][2] * len(l) + layout["espaco_apos"][c]
        for c, l in _linhas_do_cartao(bloco, layout))


def _linhas_cabecalho(titulo, orgao, layout, largura=LARGURA - 2 * MARGEM):
    """[(texto, peso, tamanho)] do cabeçalho; nos layouts compactos, órgão e data dividem
    a mesma linha quando cabem na largura."""
    t_titulo, t_orgao, t_data = layout["cabecalho"]
    atualizado = f"Atualizado em {datetime.now():%d/%m/%Y às %H:%M}"
    juntos = f"{orgao} · {atualizado}"
    if (layout["modalidade_ao_lado"]
            and _medidor.textlength(juntos, font=_fonte("normal", t_data))
            <= largura):
        return [(titulo, "negrito", t_titulo), (juntos, "normal", t_data)]
    return [(titulo, "negrito", t_titulo), (orgao, "normal", t_orgao),
            (atualizado, "semi", t_data)]


def _cabecalho(titulo, orgao, layout):
    """(altura da faixa, linhas de texto, brasão reduzido ou None, x do texto).

    O brasão fica à esquerda, reduzido proporcionalmente para caber na altura da faixa."""
    linhas = _linhas_cabecalho(titulo, orgao, layout)
    altura = 36 + sum(round(t * 1.32) for _, _, t in linhas) + 20
    imagem = brasao.para_caber(220, altura - 24)
    if imagem is None:
        return altura, linhas, None, MARGEM
    x = MARGEM + imagem.width + 24
    linhas = _linhas_cabecalho(titulo, orgao, layout, LARGURA - x - MARGEM)
    altura = max(altura, 36 + sum(round(t * 1.32) for _, _, t in linhas) + 20)
    return altura, linhas, imagem, x


def _altura_faixa(titulo, orgao, layout):
    """Altura da faixa azul do cabeçalho, calculada pelo texto."""
    return _cabecalho(titulo, orgao, layout)[0]


def _encher(alturas, limite):
    """Agrupa as alturas em páginas sem passar do limite (mantendo a ordem)."""
    paginas, atual, usado = [], [], 0
    for indice, altura in enumerate(alturas):
        if atual and usado + altura > limite:
            paginas.append(atual)
            atual, usado = [], 0
        atual.append(indice)
        usado += altura
    paginas.append(atual)
    return paginas


def _distribuir(blocos, layout, titulo, orgao):
    topo = _altura_faixa(titulo, orgao, layout) + layout["espaco"] + 10
    disponivel = ALTURA - topo - RODAPE
    alturas = [_altura(b, layout) + layout["espaco"] for b in blocos]
    paginas = _encher(alturas, disponivel)
    if len(paginas) > 1:
        # Equilibra entre as imagens (ex.: 5 + 4 em vez de 8 + 1), sem criar outras.
        alvo = sum(alturas) / len(paginas)
        for limite in range(int(alvo), disponivel + 1, 20):
            equilibradas = _encher(alturas, limite)
            if len(equilibradas) == len(paginas):
                paginas = equilibradas
                break
    return [[blocos[i] for i in pagina] for pagina in paginas]


def paginar(blocos, titulo, orgao):
    """Escolhe o layout que põe todas as licitações numa só imagem, mantendo a
    legibilidade; se não houver, usa o compacto em quantas imagens forem necessárias.
    Retorna (páginas, layout)."""
    for layout in LAYOUTS:
        paginas = _distribuir(blocos, layout, titulo, orgao)
        if len(paginas) == 1:
            return paginas, layout
    return paginas, layout


def desenhar(blocos, pagina, total, titulo, orgao, layout=LAYOUTS[0]):
    img = Image.new("RGB", (LARGURA, ALTURA), FUNDO)
    d = ImageDraw.Draw(img)

    faixa, linhas, imagem_brasao, x_texto = _cabecalho(titulo, orgao, layout)
    topo = faixa + layout["espaco"] + 10
    d.rectangle((0, 0, LARGURA, faixa), fill=PRIMARIA)
    if imagem_brasao is not None:
        img.paste(imagem_brasao, (MARGEM, (faixa - imagem_brasao.height) // 2), imagem_brasao)
    y = 36
    for indice, (texto, peso, tamanho) in enumerate(linhas):
        d.text((x_texto, y), texto, font=_fonte(peso, tamanho),
               fill="white" if indice != 1 or peso == "semi" else "#dbe6f5")
        y += round(tamanho * 1.32)
    if total > 1:
        texto = f"{pagina}/{total}"
        fonte = _fonte("negrito", 40)
        d.text((LARGURA - MARGEM - d.textlength(texto, font=fonte), 40), texto,
               font=fonte, fill="white")

    y = topo
    if not blocos:
        texto = "Não há licitações abertas no momento."
        fonte = _fonte("semi", 40)
        d.text(((LARGURA - d.textlength(texto, font=fonte)) / 2, ALTURA / 2), texto,
               font=fonte, fill=SUTIL)
    est, padding = layout["estilos"], layout["padding"]
    for bloco in blocos:
        altura = _altura(bloco, layout)
        d.rounded_rectangle((MARGEM, y, LARGURA - MARGEM, y + altura), radius=20,
                            fill=bloco["fundo"])
        d.rounded_rectangle((MARGEM, y, MARGEM + BARRA + 10, y + altura), radius=20,
                            fill=bloco["destaque"])
        d.rectangle((MARGEM + BARRA, y, MARGEM + BARRA + 12, y + altura), fill=bloco["fundo"])

        x, ty = MARGEM + BARRA + padding, y + padding
        if _modalidade_ao_lado(bloco, layout):
            # Alinha a modalidade à direita, na altura do texto do edital.
            fonte = _fonte(*est["modalidade"][:2])
            mx = LARGURA - MARGEM - padding - d.textlength(bloco["modalidade"], font=fonte)
            my = ty + est["titulo"][1] - est["modalidade"][1] - 2
            d.text((mx, my), bloco["modalidade"], font=fonte, fill=bloco["destaque"])
        for chave, linhas in _linhas_do_cartao(bloco, layout):
            peso, tamanho, passo, _ = est[chave]
            cor = {"titulo": bloco["destaque"], "modalidade": bloco["destaque"],
                   "quando": ALERTA if bloco["alerta"] else TEXTO,
                   "objeto": TEXTO, "equipe": "#344054"}[chave]
            for linha in linhas:
                d.text((x, ty), linha, font=_fonte(peso, tamanho), fill=cor)
                ty += passo
            ty += layout["espaco_apos"][chave]
        y += altura + layout["espaco"]

    rodape = f"Agenda de Licitações · {orgao}"
    if total > 1:
        rodape += f" · página {pagina} de {total}"
    fonte = _fonte("normal", 26)
    d.text(((LARGURA - d.textlength(rodape, font=fonte)) / 2, ALTURA - RODAPE + 22), rodape,
           font=fonte, fill=SUTIL)

    saida = io.BytesIO()
    img.save(saida, "PNG", optimize=True)
    return saida.getvalue()
