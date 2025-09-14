from __future__ import annotations

import argparse
import logging

from .server import HalmaServer
from .client.ui import GameClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Halma com sockets")
    parser.add_argument("--server", action="store_true", help="Executar como servidor")
    parser.add_argument("--client", action="store_true", help="Executar como cliente")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=50007)
    args = parser.parse_args()

    if args.server == args.client:
        print("Escolha exatamente um modo: --server ou --client")
        raise SystemExit(1)

    if args.server:
        logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
        HalmaServer(args.host, args.port).start()
    else:
        GameClient(args.host, args.port).run()


if __name__ == "__main__":
    main()