"""Acesso ao banco de dados SQLite."""
import sqlite3

from flask import current_app, g

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
    valor_estimado    REAL,
    status            TEXT    NOT NULL,
    suspensa_em       TEXT,               -- data e hora em que a sessão foi suspensa
    motivo_suspensao  TEXT,
    observacoes       TEXT,
    criado_por        INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em         TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    atualizado_em     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_licitacoes_data ON licitacoes(data_sessao);
CREATE INDEX IF NOT EXISTS idx_licitacoes_vigencia ON licitacoes(vigencia_ate);

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


def init_db():
    get_db().executescript(SCHEMA)


def registrar(acao, referencia=None, detalhes=None, licitacao_id=None):
    """Grava uma entrada na trilha de auditoria (sem commit)."""
    usuario = g.get("usuario")
    get_db().execute(
        "INSERT INTO historico (licitacao_id, usuario_id, acao, referencia, detalhes)"
        " VALUES (?, ?, ?, ?, ?)",
        (licitacao_id, usuario["id"] if usuario else None, acao, referencia, detalhes),
    )
