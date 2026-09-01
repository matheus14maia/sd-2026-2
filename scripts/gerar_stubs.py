#!/usr/bin/env python3
"""Gera os stubs Python a partir de proto/restaurante.proto.

Os arquivos gerados vao para src/gerado/ e nao sao versionados: o contrato
(.proto) e a fonte da verdade, os stubs sao artefato de build. Rode este script
depois de clonar o projeto ou sempre que o .proto mudar.

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

    comando = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"--proto_path={PROTO_DIR}",
        f"--python_out={SAIDA}",
        f"--pyi_out={SAIDA}",
        f"--grpc_python_out={SAIDA}",
        str(PROTO_DIR / "restaurante.proto"),
    ]
    print("Gerando stubs a partir de", PROTO_DIR / "restaurante.proto")
    resultado = subprocess.run(comando)
    if resultado.returncode != 0:
        return resultado.returncode

    # O protoc gera "import restaurante_pb2" (import absoluto). Como os stubs
    # ficam dentro do pacote src.gerado, o import precisa ser relativo ao pacote.
    grpc_stub = SAIDA / "restaurante_pb2_grpc.py"
    conteudo = grpc_stub.read_text(encoding="utf-8")
    conteudo = re.sub(
        r"^import restaurante_pb2 as",
        "from . import restaurante_pb2 as",
        conteudo,
        flags=re.MULTILINE,
    )
    grpc_stub.write_text(conteudo, encoding="utf-8")

    print("Stubs gerados em", SAIDA)
    return 0


if __name__ == "__main__":
    sys.exit(main())
