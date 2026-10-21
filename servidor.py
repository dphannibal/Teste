"""Inicia a Agenda de Licitações na rede interna.

Uso:  python servidor.py            (porta 8080 em todas as interfaces)
      python servidor.py --porta 80
"""
import argparse
import socket

from waitress import serve

from licitacoes import create_app, garantir_admin_inicial


def main():
    parser = argparse.ArgumentParser(description="Servidor da Agenda de Licitações")
    parser.add_argument("--host", default="0.0.0.0", help="Interface de rede (padrão: todas)")
    parser.add_argument("--porta", type=int, default=8080)
    args = parser.parse_args()

    app = create_app()
    senha = garantir_admin_inicial(app)
    if senha:
        print("=" * 64)
        print(" Primeiro uso: usuário administrador criado.")
        print(f"   login: admin   senha temporária: {senha}")
        print(" Ela deverá ser trocada no primeiro acesso.")
        print("=" * 64)

    nome = socket.gethostname()
    print(f"Agenda de Licitações disponível em http://{nome}:{args.porta}/")
    serve(app, host=args.host, port=args.porta, threads=8)


if __name__ == "__main__":
    main()
