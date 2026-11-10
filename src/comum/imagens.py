"""Fotos dos pratos: tipo pelo conteudo, limite de tamanho e versao.

O tipo vem dos primeiros bytes do arquivo (assinatura), nao do nome nem do
Content-Type que o navegador declarou: um .exe renomeado para .jpg nao passa.
Usado pelo Gateway (borda), pelo Catalogo (dono das fotos) e pelo migrador
(fotos iniciais de db/fotos/).
"""

import hashlib
import os

TIPOS_ACEITOS = ("image/jpeg", "image/png", "image/webp")
FOTO_MAXIMO_BYTES = int(os.getenv("FOTO_MAXIMO_KB", "2048")) * 1024


def tipo_da_imagem(conteudo: bytes) -> str:
    """Tipo MIME pela assinatura do arquivo; '' se nao for JPEG, PNG nem WebP."""
    if conteudo.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if conteudo.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP":
        return "image/webp"
    return ""


def versao_da_foto(conteudo: bytes) -> str:
    """12 hex do SHA-256: a mesma foto tem sempre a mesma versao (e a mesma URL)."""
    return hashlib.sha256(conteudo).hexdigest()[:12]
