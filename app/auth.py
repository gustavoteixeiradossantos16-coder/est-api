"""Autenticação: toda rota de usuário exige o token do Firebase no cabeçalho.

    Authorization: Bearer <idToken do Firebase Auth>
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Header

from .errors import AppError
from .firebase import verify_id_token

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CurrentUser:
    uid: str
    email: str | None


def get_current_user(authorization: str = Header(default="")) -> CurrentUser:
    if not authorization.lower().startswith("bearer "):
        raise AppError(401, "NAO_AUTENTICADO", "Faça login para continuar.")
    try:
        decoded = verify_id_token(authorization[7:].strip())
    except Exception as e:  # token expirado, inválido ou de outro projeto
        log.info("Token rejeitado: %s", e)
        raise AppError(401, "NAO_AUTENTICADO", "Sua sessão expirou. Entre novamente.") from e
    return CurrentUser(uid=decoded["uid"], email=decoded.get("email"))
