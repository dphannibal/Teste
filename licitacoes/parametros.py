"""Parâmetros configuráveis: nome do órgão, modalidades, situações e permissões.

Lidos do banco uma vez por requisição (cache em ``g``) e invalidados ao salvar.
"""
from flask import g

from .db import get_db
from .perfis import PERFIL_TOTAL, PERMISSOES


def _cache():
    if "parametros" not in g:
        conn = get_db()
        modalidades = [dict(m) for m in conn.execute(
            "SELECT * FROM modalidades ORDER BY ordem, nome")]
        situacoes = [dict(s) for s in conn.execute(
            "SELECT * FROM situacoes ORDER BY ordem, nome")]
        permissoes = {}
        for perfil, permissao in conn.execute("SELECT perfil, permissao FROM permissoes"):
            permissoes.setdefault(perfil, set()).add(permissao)
        permissoes[PERFIL_TOTAL] = set(PERMISSOES)
        g.parametros = {
            "modalidades": modalidades,
            "modalidade": {m["nome"]: m for m in modalidades},
            "situacoes": situacoes,
            "situacao": {s["chave"]: s for s in situacoes},
            "permissoes": permissoes,
            "config": dict(conn.execute("SELECT chave, valor FROM configuracoes").fetchall()),
        }
    return g.parametros


def invalidar():
    g.pop("parametros", None)


def nome_orgao():
    return _cache()["config"].get("nome_orgao") or "Secretaria"


def tem_permissao(perfil, permissao):
    return permissao in _cache()["permissoes"].get(perfil, set())


def permissoes():
    return _cache()["permissoes"]


# --- Modalidades -------------------------------------------------------------------------

def modalidades(somente_ativas=False, incluir=None):
    """Lista de modalidades (dicts). ``incluir`` mantém uma inativa já em uso."""
    return [m for m in _cache()["modalidades"]
            if not somente_ativas or m["ativa"] or m["nome"] == incluir]


def modalidade(nome):
    return _cache()["modalidade"].get(nome) or {
        "nome": nome, "sigla": "", "cor": "#4b5563", "credenciamento": 0,
        "exige_equipe": 1, "rotulo_condutor": "Agente de contratação", "ordem": 999,
    }


def eh_credenciamento(nome):
    return bool(modalidade(nome)["credenciamento"])


def clarear(cor, fator=0.88):
    """Mistura a cor com branco: usada para os fundos suaves."""
    cor = cor.lstrip("#")
    r, g_, b = (int(cor[i:i + 2], 16) for i in (0, 2, 4))
    return "#" + "".join(f"{round(c + (255 - c) * fator):02x}" for c in (r, g_, b))


def cores_modalidade(nome):
    """(fundo suave, cor de destaque)."""
    cor = modalidade(nome)["cor"]
    return clarear(cor), cor


def edital(lic):
    """Número do edital com a sigla da modalidade (ex.: PE 007/2026)."""
    if not lic["numero_edital"]:
        return f"Proc. {lic['numero_processo']}"
    sigla = modalidade(lic["modalidade"])["sigla"]
    return f"{sigla} {lic['numero_edital']}".strip()


# --- Situações ---------------------------------------------------------------------------

def situacoes(somente_ativas=False, incluir=None):
    return [s for s in _cache()["situacoes"]
            if not somente_ativas or s["ativa"] or s["chave"] == incluir]


def situacao(chave):
    return _cache()["situacao"].get(chave) or {
        "chave": chave, "nome": chave or "—", "cor": "#475467", "fase": "", "ordem": 999,
        "sistema": 0, "ativa": 0,
    }


def fase(chave):
    return situacao(chave)["fase"]


def chaves(*fases):
    """Chaves das situações nas fases informadas (para filtros SQL)."""
    return [s["chave"] for s in _cache()["situacoes"] if s["fase"] in fases] or [""]


def cores_situacao(chave):
    cor = situacao(chave)["cor"]
    return clarear(cor, 0.82), cor
