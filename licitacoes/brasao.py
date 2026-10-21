"""Brasão do município: guardado como PNG e reduzido proporcionalmente quando não cabe."""
import os

from flask import current_app
from PIL import Image, UnidentifiedImageError

ARQUIVO = "brasao.png"
# Ao guardar, limita o maior lado; nos cabeçalhos ele é reduzido de novo para caber.
LADO_MAXIMO = 600


def caminho():
    return os.path.join(current_app.config["PASTA_ARQUIVOS"], ARQUIVO)


def existe():
    return os.path.exists(caminho())


def versao():
    """Muda a cada novo envio, para o navegador não usar a imagem antiga em cache."""
    return int(os.path.getmtime(caminho())) if existe() else 0


def salvar(arquivo):
    """Valida e guarda a imagem enviada. ValueError se não for uma imagem."""
    try:
        imagem = Image.open(arquivo)
        imagem.load()
    except (UnidentifiedImageError, OSError) as erro:
        raise ValueError("O arquivo enviado não é uma imagem válida (use PNG, JPG ou WebP).") \
            from erro
    imagem = imagem.convert("RGBA")
    imagem.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    os.makedirs(os.path.dirname(caminho()), exist_ok=True)
    imagem.save(caminho(), "PNG", optimize=True)


def remover():
    if existe():
        os.remove(caminho())


def para_caber(largura_maxima, altura_maxima):
    """Brasão reduzido proporcionalmente para caber no espaço (nunca ampliado)."""
    if not existe():
        return None
    imagem = Image.open(caminho()).convert("RGBA")
    imagem.thumbnail((largura_maxima, altura_maxima))
    return imagem
