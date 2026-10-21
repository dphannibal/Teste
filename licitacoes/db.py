"""Acesso ao banco de dados SQLite."""
import re
import sqlite3

from flask import current_app, g

from . import perfis

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nome          TEXT    NOT NULL,
    login         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    email         TEXT,
    senha_hash    TEXT    NOT NULL,
    perfil        TEXT    NOT NULL,
    ativo         INTEGER NOT NULL DEFAULT 1,
    trocar_senha  INTEGER NOT NULL DEFAULT 1,
    preferencias  TEXT,                   -- JSON: colunas e ordenação das tabelas
    criado_em     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS servidores (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nome       TEXT    NOT NULL,
    matricula  TEXT,
    vinculo    TEXT    NOT NULL,
    ativo      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS licitacoes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_processo   TEXT    NOT NULL,
    numero_edital     TEXT,
    modalidade        TEXT    NOT NULL,
    objeto            TEXT    NOT NULL,
    data_publicacao   TEXT,               -- data de publicação do edital
    data_sessao       TEXT,               -- sessão pública (não se aplica a credenciamento)
    vigencia_ate      TEXT,               -- credenciamento: vencimento da vigência anual
    local             TEXT,
    agente_id         INTEGER REFERENCES servidores(id) ON DELETE SET NULL,
    membro1_id        INTEGER REFERENCES servidores(id) ON DELETE SET NULL,
    membro2_id        INTEGER REFERENCES servidores(id) ON DELETE SET NULL,
    membro3_id        INTEGER REFERENCES servidores(id) ON DELETE SET NULL,  -- opcional, raro
    valor_estimado    REAL,
    status            TEXT    NOT NULL,
    suspensa_em       TEXT,               -- data e hora em que a sessão foi suspensa
    motivo_suspensao  TEXT,
    ocorrencia        TEXT,               -- última suspensão/remarcação (ver perfis.OCORRENCIAS)
    impedimentos_mantidos TEXT,           -- ids de afastamentos aceitos com a sessão em andamento
    observacoes       TEXT,
    criado_por        INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em         TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    atualizado_em     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_licitacoes_data ON licitacoes(data_sessao);
CREATE INDEX IF NOT EXISTS idx_licitacoes_vigencia ON licitacoes(vigencia_ate);

CREATE TABLE IF NOT EXISTS afastamentos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    servidor_id  INTEGER NOT NULL REFERENCES servidores(id) ON DELETE CASCADE,
    tipo         TEXT    NOT NULL,
    inicio       TEXT    NOT NULL,
    fim          TEXT    NOT NULL,
    observacao   TEXT
);

CREATE INDEX IF NOT EXISTS idx_afastamentos_periodo ON afastamentos(inicio, fim);

CREATE TABLE IF NOT EXISTS configuracoes (
    chave  TEXT PRIMARY KEY,
    valor  TEXT
);

CREATE TABLE IF NOT EXISTS modalidades (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    nome             TEXT    NOT NULL UNIQUE,
    sigla            TEXT    NOT NULL,
    cor              TEXT    NOT NULL,
    ordem            INTEGER NOT NULL DEFAULT 0,
    ativa            INTEGER NOT NULL DEFAULT 1,
    credenciamento   INTEGER NOT NULL DEFAULT 0,  -- aberta, sem sessão, vigência anual
    exige_equipe     INTEGER NOT NULL DEFAULT 1,
    rotulo_condutor  TEXT    NOT NULL DEFAULT 'Agente de contratação'
);

CREATE TABLE IF NOT EXISTS situacoes (
    chave    TEXT    PRIMARY KEY,
    nome     TEXT    NOT NULL UNIQUE,
    cor      TEXT    NOT NULL,
    fase     TEXT    NOT NULL,
    ordem    INTEGER NOT NULL DEFAULT 0,
    ativa    INTEGER NOT NULL DEFAULT 1,
    sistema  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS permissoes (
    perfil     TEXT NOT NULL,
    permissao  TEXT NOT NULL,
    PRIMARY KEY (perfil, permissao)
);

CREATE TABLE IF NOT EXISTS historico (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    licitacao_id  INTEGER REFERENCES licitacoes(id) ON DELETE SET NULL,
    usuario_id    INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    acao          TEXT    NOT NULL,
    referencia    TEXT,
    detalhes      TEXT,
    data          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_historico_licitacao ON historico(licitacao_id);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Colunas acrescentadas depois da primeira versão: bancos já em uso as recebem na partida.
COLUNAS_NOVAS = {
    "licitacoes": {
        "membro3_id": "INTEGER REFERENCES servidores(id) ON DELETE SET NULL",
        "ocorrencia": "TEXT",
        "impedimentos_mantidos": "TEXT",
    },
    "usuarios": {
        "preferencias": "TEXT",
    },
}


def _semear_parametros(conn):
    """Valores iniciais de modalidades, situações, permissões e nome do órgão."""
    if not conn.execute("SELECT 1 FROM modalidades LIMIT 1").fetchone():
        for ordem, (nome, sigla, cor, cred, equipe, condutor) in enumerate(
                perfis.MODALIDADES_PADRAO):
            conn.execute(
                "INSERT INTO modalidades (nome, sigla, cor, ordem, credenciamento,"
                " exige_equipe, rotulo_condutor) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nome, sigla, cor, ordem, cred, equipe, condutor),
            )
    if not conn.execute("SELECT 1 FROM situacoes LIMIT 1").fetchone():
        for ordem, (chave, nome, cor, fase, sistema) in enumerate(perfis.SITUACOES_PADRAO):
            conn.execute(
                "INSERT INTO situacoes (chave, nome, cor, fase, ordem, sistema)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (chave, nome, cor, fase, ordem, sistema),
            )
    if not conn.execute("SELECT 1 FROM permissoes LIMIT 1").fetchone():
        for perfil, permissoes in perfis.PERMISSOES_PADRAO.items():
            for permissao in permissoes:
                conn.execute("INSERT INTO permissoes VALUES (?, ?)", (perfil, permissao))
    conn.execute(
        "INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES ('nome_orgao', ?)",
        (current_app.config.get("NOME_ORGAO", "Secretaria"),),
    )


def _migrar_para_parametros(conn):
    """Bancos da versão anterior: situação por nome, edital com sigla, perfil 'operador'."""
    nomes = {nome: chave for chave, nome, *_ in perfis.SITUACOES_PADRAO}
    for nome, chave in nomes.items():
        conn.execute("UPDATE licitacoes SET status = ? WHERE status = ?", (chave, nome))
    conn.execute("UPDATE usuarios SET perfil = 'pregoeiro' WHERE perfil = 'operador'")
    # O edital passa a ser só o número; a sigla vem da modalidade nas visualizações.
    for id_, numero in conn.execute(
            "SELECT id, numero_edital FROM licitacoes WHERE numero_edital IS NOT NULL").fetchall():
        limpo = re.sub(r"^[A-Za-zÀ-ú]+\s*", "", numero).strip()
        if limpo != numero:
            conn.execute("UPDATE licitacoes SET numero_edital = ? WHERE id = ?", (limpo, id_))


# Migrações de dados, aplicadas uma única vez (controle por PRAGMA user_version).
MIGRACOES = [_migrar_para_parametros]


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    for tabela, colunas in COLUNAS_NOVAS.items():
        existentes = {c["name"] for c in conn.execute(f"PRAGMA table_info({tabela})")}
        for nome, tipo in colunas.items():
            if nome not in existentes:
                conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")
    _semear_parametros(conn)
    versao = conn.execute("PRAGMA user_version").fetchone()[0]
    for numero, migracao in enumerate(MIGRACOES, start=1):
        if versao < numero:
            migracao(conn)
            conn.execute(f"PRAGMA user_version = {numero}")
    conn.commit()


def registrar(acao, referencia=None, detalhes=None, licitacao_id=None):
    """Grava uma entrada na trilha de auditoria (sem commit)."""
    usuario = g.get("usuario")
    get_db().execute(
        "INSERT INTO historico (licitacao_id, usuario_id, acao, referencia, detalhes)"
        " VALUES (?, ?, ?, ?, ?)",
        (licitacao_id, usuario["id"] if usuario else None, acao, referencia, detalhes),
    )
