# Agenda de Licitações

Sistema web para a **intranet da secretaria** que organiza a agenda de sessões de licitação,
com controle de acesso por perfil de usuário e trilha de auditoria.

## Funcionalidades

- **Painel**: sessões de hoje, próximas sessões (30 dias), totais por situação e alerta de
  sessões que já passaram sem desfecho registrado.
- **Calendário mensal** com as sessões coloridas pela situação.
- **Cadastro de licitações**: nº do processo e do edital, modalidade (Lei nº 14.133/2021),
  objeto, data/hora da sessão, local/plataforma, responsável (pregoeiro / agente de
  contratação), valor estimado, situação e observações.
- **Busca e filtros** por texto, modalidade, situação, responsável e período.
- **Exportação .ics** da agenda (filtrada) para Outlook, Google Agenda, Thunderbird etc.
- **Histórico** de alterações em cada licitação e **auditoria** geral (logins, cadastros,
  alterações, exclusões, gestão de usuários).
- **Gestão de usuários**: cadastro, troca de perfil, desativação e redefinição de senha.
  Senhas temporárias precisam ser trocadas no primeiro acesso.

## Perfis de acesso

| Permissão                       | Administrador | Gestor | Operador | Consulta |
|---------------------------------|:-------------:|:------:|:--------:|:--------:|
| Ver painel, calendário e lista  | ✔ | ✔ | ✔ | ✔ |
| Cadastrar e editar licitações   | ✔ | ✔ | ✔ |   |
| Excluir licitações              | ✔ | ✔ |   |   |
| Consultar auditoria             | ✔ | ✔ |   |   |
| Gerenciar usuários              | ✔ |   |   |   |

As regras ficam em `licitacoes/perfis.py` (dicionário `PERMISSOES`) e podem ser ajustadas
à realidade da secretaria. O mesmo arquivo define as modalidades e situações.

## Instalação no servidor da intranet

Requisito: Python 3.10 ou superior (Windows ou Linux). Não é preciso instalar banco de
dados: os dados ficam em um arquivo SQLite na pasta `instance/`.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux: source .venv/bin/activate
pip install -r requirements.txt
python servidor.py --porta 8080
```

Na primeira execução é criado o usuário **admin** e a senha temporária aparece no
terminal (ou defina-a antes com a variável de ambiente `ADMIN_PASSWORD`). Os demais
servidores da secretaria acessam por `http://NOME-DO-SERVIDOR:8080/`.

Se precisar recuperar o acesso de administrador:

```bash
flask --app licitacoes criar-admin --login admin
```

### Configuração opcional (variáveis de ambiente)

| Variável         | Uso                                                                  |
|------------------|----------------------------------------------------------------------|
| `NOME_ORGAO`     | Nome exibido no topo das páginas (ex.: "Secretaria de Administração") |
| `ADMIN_PASSWORD` | Senha inicial do admin no primeiro uso                               |
| `SECRET_KEY`     | Chave das sessões; se omitida, é gerada em `instance/secret_key`     |

### Recomendações

- **Backup**: copie periodicamente a pasta `instance/` (contém o banco `licitacoes.sqlite3`).
- **Firewall**: libere a porta escolhida apenas para a rede interna.
- **Serviço**: para iniciar junto com o servidor, use o Agendador de Tarefas / NSSM no
  Windows, ou um serviço `systemd` no Linux.
- **HTTPS**: se a intranet tiver certificado, coloque o sistema atrás do IIS, Nginx ou
  Apache como proxy reverso.

## Desenvolvimento

```bash
pip install -r requirements.txt pytest
python -m pytest
```

Estrutura:

```
servidor.py              inicia o servidor (Waitress)
licitacoes/
  __init__.py            criação da aplicação, CSRF, filtros, comandos
  perfis.py              perfis, permissões, modalidades e situações
  auth.py                login, troca de senha e controle de acesso
  agenda.py              painel, calendário, cadastro e exportação .ics
  admin.py               usuários e auditoria
  db.py                  esquema e acesso ao SQLite
  templates/, static/    telas
tests/                   testes automatizados
```
