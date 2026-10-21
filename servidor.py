"""Inicia a Agenda de Licitações na rede interna.

Uso:  python servidor.py                         (porta 8080 em todas as interfaces)
      python servidor.py --porta 80
      python servidor.py --dados "C:\\ProgramData\\AgendaLicitacoes"

Instalação em pasta compartilhada: o programa fica na pasta compartilhada e roda no
computador que a hospeda. Ao iniciar, ele cria na própria pasta o atalho
"Abrir Agenda de Licitações", que os demais usuários abrem pela rede. Os dados ficam
na pasta indicada em --dados, que NÃO deve ser compartilhada.
"""
import argparse
import os
import socket

from waitress import serve

from licitacoes import create_app, garantir_admin_inicial

PASTA_PROGRAMA = os.path.dirname(os.path.abspath(__file__))
NOME_ATALHO = "Abrir Agenda de Licitações.url"


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
    args = parser.parse_args()

    app = create_app({"PASTA_DADOS": args.dados} if args.dados else None)
    dados = app.config["PASTA_DADOS"]
    senha = garantir_admin_inicial(app)
    if senha:
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

    print(f"Dados (banco, chave e brasão): {dados}")
    if os.path.commonpath([os.path.abspath(dados), PASTA_PROGRAMA]) == PASTA_PROGRAMA:
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
