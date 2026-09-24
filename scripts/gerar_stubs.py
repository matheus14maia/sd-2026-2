#!/usr/bin/env python3
"""Gera os stubs Python a partir de todos os arquivos proto/*.proto.

Os arquivos gerados vao para src/gerado/ e nao sao versionados: os contratos
(.proto) sao a fonte da verdade, os stubs sao artefato de build. Rode este
script depois de clonar o projeto ou sempre que um .proto mudar.

    python scripts/gerar_stubs.py
"""

import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PROTO_DIR = RAIZ / "proto"
SAIDA = RAIZ / "src" / "gerado"


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "__init__.py").touch()

    # Remove stubs antigos para nao sobrar arquivo de um .proto que ja saiu.
    for antigo in SAIDA.glob("*_pb2*.py*"):
        antigo.unlink()

    protos = sorted(PROTO_DIR.glob("*.proto"))
    if not protos:
        print("Nenhum .proto encontrado em", PROTO_DIR)
        return 1

    comando = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"--proto_path={PROTO_DIR}",
        f"--python_out={SAIDA}",
        f"--pyi_out={SAIDA}",
        f"--grpc_python_out={SAIDA}",
        *[str(proto) for proto in protos],
    ]
    print("Gerando stubs de:", ", ".join(proto.name for proto in protos))
    resultado = subprocess.run(comando)
    if resultado.returncode != 0:
        return resultado.returncode

    # O protoc gera "import catalogo_pb2 as ..." (import absoluto). Como os
    # stubs ficam dentro do pacote src.gerado, o import precisa ser relativo.
    for grpc_stub in SAIDA.glob("*_pb2_grpc.py"):
        conteudo = grpc_stub.read_text(encoding="utf-8")
        conteudo = re.sub(
            r"^import (\w+_pb2) as",
            r"from . import \1 as",
            conteudo,
            flags=re.MULTILINE,
        )
        grpc_stub.write_text(conteudo, encoding="utf-8")

    print("Stubs gerados em", SAIDA)
    return 0


if __name__ == "__main__":
    sys.exit(main())
