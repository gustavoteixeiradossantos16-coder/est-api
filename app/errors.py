"""Erros da aplicação com mensagem pronta para mostrar ao usuário."""
from __future__ import annotations


class AppError(Exception):
    """Erro com status HTTP, código estável (para o front) e mensagem em português."""

    def __init__(self, status: int, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem


def entrada_invalida(mensagem: str) -> AppError:
    return AppError(400, "ENTRADA_INVALIDA", mensagem)
