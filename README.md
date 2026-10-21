# Agenda de Licitações

Sistema web para a **intranet da secretaria** que organiza a agenda de sessões de licitação,
com controle de acesso por perfil de usuário e trilha de auditoria.

## Funcionalidades

- **Painel**: cada usuário escolhe as **colunas, a ordem delas e o critério de
  ordenação** (também clicando no título da coluna). O quadro **Licitações em andamento**
  reúne editais publicados, remarcadas e sessões abertas, inclusive as suspensas depois de
  abertas para análise documental; as suspensas antes da abertura ficam em quadro próprio.
  O **número do edital** (PE 007/2026, CE 075/2025…) é o destaque de cada
  linha, e as linhas têm **cores suaves por modalidade** (pregão eletrônico em verde,
  pregão presencial em vermelho, concorrência eletrônica em azul etc.). Cada linha mostra
  a equipe (pregoeiro/agente e os dois membros; o terceiro só aparece se escalado).
  Mostra sessões de hoje, todas as próximas sessões (sem limite de prazo, pois há
  editais publicados com mais de 30 dias de antecedência), suspensas sem data definida,
  credenciamentos abertos com alerta de renovação, totais por situação e sessões que já
  passaram sem desfecho registrado.
- **Calendário mensal** com as sessões coloridas pela situação.
- **Cadastro de licitações**: nº do processo e do edital, modalidade (Lei nº 14.133/2021),
  objeto, publicação do edital, data/hora da sessão, local/plataforma, equipe, valor
  estimado, situação e observações.
- **Credenciamento**: fica aberto por tempo indeterminado, sem sessão; tem vigência anual
  (padrão: 1 ano após a publicação) renovada pelo botão “Renovar por 1 ano”. Só admite as
  situações “Em andamento” e “Concluída”.
- **Equipe**: pregoeiro ou agente de contratação e mais dois membros, além de um terceiro
  membro opcional, escolhidos no cadastro de **servidores** (com vínculo funcional). O sistema **impede salvar uma equipe
  com minoria de efetivos** (maioria estrita de efetivos ou empregados públicos do quadro
  permanente: 2 de 3, ou 3 de 4 com o terceiro membro) e exige a equipe completa fora da fase de planejamento (exceto
  inexigibilidade).
- **Férias e afastamentos**: registrados por servidor. O sistema impede escalar quem
  estará afastado na data da sessão; se a sessão **já estiver em andamento**, avisa e
  permite **trocar ou manter** o membro (a decisão vai para o histórico). O sistema alerta
  na licitação quando um afastamento lançado depois atinge uma equipe já escalada.
- **Suspender / remarcar**, conforme a fase da sessão pública:
  - antes da abertura: *suspensa sem data definida*, *remarcada* ou *remarcada após
    retificação do edital*;
  - com a sessão aberta (em andamento): *suspensa para análise documental* ou
    *remarcada pelo pregoeiro (continuação)* em outro dia.
  Todas exigem data e hora e ficam no histórico.
- **WhatsApp em imagem**: gera imagens no formato de tela de celular (1080 × 1920) com as
  licitações abertas ou em andamento — número do edital, modalidade, data e horário,
  objeto e equipe —, nas cores da modalidade. O sistema escolhe o layout mais compacto que
  ainda mantém a leitura (nenhum texto abaixo de 26 px) para caber o maior número de
  licitações numa só imagem; se não couberem, divide em imagens equilibradas. Também
  há imagem individual por licitação e, se preferir, o mesmo conteúdo em texto.
- **Busca e filtros** por texto, modalidade, situação, responsável e período.
- **Exportação .ics** da agenda (filtrada) para Outlook, Google Agenda, Thunderbird etc.
- **Histórico** de alterações em cada licitação e **auditoria** geral (logins, cadastros,
  alterações, exclusões, gestão de usuários).
- **Gestão de usuários**: cadastro, troca de perfil, desativação e redefinição de senha.
  Senhas temporárias precisam ser trocadas no primeiro acesso.

## Perfis de acesso

Perfis: **Administrador**, **Gestor**, **Pregoeiro / Agente de Contratação** e **Consulta**.
O que cada perfil pode fazer é definido pelo Administrador em **Configurações → Permissões
dos perfis** (o Administrador sempre tem tudo). Padrão inicial:

| Permissão                                   | Administrador | Gestor | Pregoeiro / Agente | Consulta |
|---------------------------------------------|:-:|:-:|:-:|:-:|
| Ver painel, calendário e licitações         | ✔ | ✔ | ✔ | ✔ |
| Cadastrar e editar licitações               | ✔ | ✔ | ✔ |   |
| Suspender e remarcar sessões                | ✔ | ✔ | ✔ |   |
| Excluir licitações                          | ✔ | ✔ |   |   |
| Cadastrar servidores                        | ✔ | ✔ |   |   |
| Registrar férias e afastamentos             | ✔ | ✔ |   |   |
| Consultar auditoria                         | ✔ | ✔ |   |   |
| Alterar parâmetros (órgão, modalidades, situações) | ✔ | ✔ |   |   |
| Gerenciar usuários                          | ✔ |   |   |   |

## Feriados, pontos facultativos e prazo mínimo legal

- Já vêm cadastrados os feriados **nacionais**, o **estadual do RJ** (São Jorge, 23/04 — Lei
  estadual 5.198/2008) e os **municipais de Três Rios** (São Sebastião, 20/01, e Emancipação,
  26/12), além dos pontos facultativos usuais (Carnaval, Quarta de Cinzas, Corpus Christi,
  Dia do Servidor). Confira a lista com a legislação local e ajuste em **Configurações →
  Feriados e pontos facultativos**.
- É possível cadastrar feriados ou pontos facultativos (fixos, móveis pela Páscoa ou numa data
  específica) e **transferir a data** de um feriado num ano (ex.: decreto municipal que
  antecipa o feriado), registrando o ato. Ao cadastrar ou transferir, o sistema avisa se já
  há sessão marcada no dia.
- A data da sessão (no cadastro, na edição e nas remarcações) **não pode cair em sábado,
  domingo ou feriado**; em ponto facultativo, só com a confirmação de que haverá expediente.
- **Prazo mínimo legal** (art. 55 da Lei 14.133/2021; dispensa: art. 75, § 3º; diálogo
  competitivo: art. 32, § 1º, I): cada licitação tem o enquadramento do prazo (sugerido pela
  modalidade). A contagem começa no dia útil seguinte à divulgação do edital (art. 183,
  § 1º, I), considera apenas dias úteis (sem fins de semana, feriados e pontos facultativos)
  e garante os dias completos — a sessão pode ocorrer no dia útil seguinte ao último dia do
  prazo. O formulário mostra a data mínima enquanto se preenche.
- **Remarcação após retificação do edital**: o prazo é contado de novo a partir da divulgação
  do edital retificado (art. 55, § 1º), salvo quando se marca que a alteração não compromete
  a formulação das propostas.

## Parâmetros (Configurações)

Quem tem a permissão de parâmetros (Administrador e Gestor, por padrão) altera:

- **Nome da secretaria/órgão** exibido no cabeçalho e nas imagens.
- **Modalidades**: nome, **sigla**, cor, ordem, se exige equipe, quem conduz (pregoeiro ou
  agente) e se funciona como credenciamento. O número do edital é digitado **sem a sigla**
  (ex.: `007/2026`) e aparece nas telas como `PE 007/2026`.
- **Situações da licitação**: nome, cor, ordem e fase. O comportamento segue a fase
  (planejamento, publicada, remarcada, suspensa, em andamento, concluída, encerrada). As
  situações do sistema podem ser renomeadas e recoloridas, mas não excluídas.

Tudo fica registrado na auditoria.

## Instalação no servidor da intranet

Ao atualizar uma instalação existente, rode de novo `pip install -r requirements.txt`
(a imagem do WhatsApp usa a biblioteca Pillow). O banco é atualizado sozinho na partida.

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

Primeiros passos: cadastre os usuários (menu **Usuários**) e os servidores que compõem as
equipes (menu **Servidores**) antes de lançar as licitações.

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
  perfis.py              perfis e valores padrão dos parâmetros
  auth.py                login, troca de senha e controle de acesso
  agenda.py              painel, calendário, cadastro, suspensão, WhatsApp e .ics
  admin.py               usuários, servidores, afastamentos e auditoria
  parametros.py          leitura dos parâmetros (modalidades, situações, permissões)
  config.py              telas de configuração (permissões e parâmetros)
  feriados.py            feriados, dias úteis e prazo mínimo legal
  equipe.py              regras da equipe (efetivos, férias e afastamentos)
  imagem.py              imagem para WhatsApp (fonte Inter em static/fontes, licença OFL)
  db.py                  esquema e acesso ao SQLite
  templates/, static/    telas
tests/                   testes automatizados
```
