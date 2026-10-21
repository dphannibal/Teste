"""Inicia a Agenda de Licitações na rede interna.

Uso:  python servidor.py                         (porta 8080 em todas as interfaces)
      python servidor.py --porta 80
      python servidor.py --dados "C:\\ProgramData\\AgendaLicitacoes"
      AgendaLicitacoes.exe                       (versão instalada no Windows)

Instalação em pasta compartilhada: o programa fica na pasta compartilhada e roda no
computador que a hospeda. Ao iniciar, ele cria na própria pasta o atalho
"Abrir Agenda de Licitações", que os demais usuários abrem pela rede. Os dados ficam
na pasta indicada em --dados, que NÃO deve ser compartilhada.
"""
import argparse
import os
import socket
import sys

from waitress import serve

from licitacoes import __version__, create_app, garantir_admin_inicial

# Empacotado pelo instalador (PyInstaller), o programa é o AgendaLicitacoes.exe.
EMPACOTADO = getattr(sys, "frozen", False)
PASTA_PROGRAMA = os.path.dirname(os.path.abspath(sys.executable if EMPACOTADO else __file__))
NOME_ATALHO = "Abrir Agenda de Licitações.url"
# Pasta de dados padrão da versão instalada: fora da pasta do programa (compartilhada).
DADOS_INSTALADO = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                               "AgendaLicitacoes")


class _Duplicar:
    """Escreve a saída na tela e no arquivo de registro (o serviço roda sem janela)."""

    def __init__(self, *destinos):
        self.destinos = [d for d in destinos if d is not None]

    def write(self, texto):
        for destino in self.destinos:
            destino.write(texto)
            destino.flush()

    def flush(self):
        for destino in self.destinos:
            destino.flush()


def enderecos_ipv4():
    """Endereços IPv4 deste computador na rede (sem o 127.0.0.1)."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        # Descobre a interface usada para sair para a rede (nenhum pacote é enviado).
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def criar_atalho(pasta, url):
    """Atalho de internet do Windows: abre o sistema no navegador com dois cliques."""
    caminho = os.path.join(pasta, NOME_ATALHO)
    with open(caminho, "w", encoding="utf-8", newline="\r\n") as arquivo:
        arquivo.write(f"[InternetShortcut]\nURL={url}\n")
    return caminho


def main():
    parser = argparse.ArgumentParser(description="Servidor da Agenda de Licitações")
    parser.add_argument("--host", default="0.0.0.0", help="Interface de rede (padrão: todas)")
    parser.add_argument("--porta", type=int, default=8080)
    parser.add_argument("--dados", help="Pasta do banco de dados, da chave das sessões e do "
                                        "brasão (fora da pasta compartilhada)")
    parser.add_argument("--endereco", help="Endereço gravado no atalho (padrão: nome deste "
                                           "computador). Ex.: 192.168.0.10")
    parser.add_argument("--log", help="Arquivo onde também gravar as mensagens do servidor")
    parser.add_argument("--preparar", action="store_true",
                        help="Só cria o banco, o administrador e o atalho, e encerra "
                             "(usado pelo instalador)")
    parser.add_argument("--senha-em", help="Com --preparar: arquivo onde gravar a senha "
                                           "temporária do admin")
    parser.add_argument("--versao", action="version",
                        version=f"Agenda de Licitações {__version__}")
    args = parser.parse_args()

    dados_padrao = DADOS_INSTALADO if EMPACOTADO else None
    pasta_dados = args.dados or os.environ.get("AGENDA_DADOS") or dados_padrao
    app = create_app({"PASTA_DADOS": pasta_dados} if pasta_dados else None)
    dados = app.config["PASTA_DADOS"]
    registro = args.log or (os.path.join(dados, "servidor.log") if EMPACOTADO else None)
    if registro:
        arquivo = open(registro, "a", encoding="utf-8")
        sys.stdout = _Duplicar(sys.stdout, arquivo)
        sys.stderr = _Duplicar(sys.stderr, arquivo)
    print(f"Agenda de Licitações {__version__}")

    senha = garantir_admin_inicial(app)
    if senha and args.senha_em:
        with open(args.senha_em, "w", encoding="utf-8") as saida:
            saida.write(senha)
    if senha and not args.senha_em:  # com --senha-em, a senha não vai para o registro
        print("=" * 64)
        print(" Primeiro uso: usuário administrador criado.")
        print(f"   login: admin   senha temporária: {senha}")
        print(" Ela deverá ser trocada no primeiro acesso.")
        print("=" * 64)

    endereco = args.endereco or socket.gethostname()
    porta = "" if args.porta == 80 else f":{args.porta}"
    url = f"http://{endereco}{porta}/"
    try:
        atalho = criar_atalho(PASTA_PROGRAMA, url)
        print(f"Atalho para os usuários: {atalho}")
    except OSError as erro:
        print(f"Não foi possível criar o atalho na pasta do programa: {erro}")

    if args.preparar:
        print(f"Dados preparados em {dados}")
        return

    print(f"Dados (banco, chave e brasão): {dados}")
    try:
        dentro = os.path.commonpath([os.path.abspath(dados), PASTA_PROGRAMA]) == PASTA_PROGRAMA
    except ValueError:  # discos diferentes no Windows
        dentro = False
    if dentro:
        print("ATENÇÃO: a pasta de dados está dentro da pasta do programa. Se esta pasta for "
              "compartilhada, use --dados com uma pasta que não seja compartilhada.")
    print(f"Agenda de Licitações disponível em {url}")
    for ip in enderecos_ipv4():
        print(f"   ou http://{ip}{porta}/")
    print("Deixe esta janela aberta enquanto o sistema estiver em uso.")
    # Cada usuário conectado é atendido em paralelo (até 16 requisições ao mesmo tempo).
    serve(app, host=args.host, port=args.porta, threads=16)


if __name__ == "__main__":
    main()
