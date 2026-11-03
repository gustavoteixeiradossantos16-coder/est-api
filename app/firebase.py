"""Inicialização do Firebase Admin (verificação de login e acesso ao Firestore)."""
from __future__ import annotations

import json
import os
from functools import lru_cache

import firebase_admin
from firebase_admin import auth, credentials, firestore

from .config import get_settings


@lru_cache
def get_firebase_app() -> firebase_admin.App:
    s = get_settings()
    valor = s.firebase_service_account.strip()
    options = {"projectId": s.firebase_project_id}
    if valor.startswith("{"):
        cred = credentials.Certificate(json.loads(valor))  # JSON colado na variável de ambiente
    elif os.path.isfile(valor):
        cred = credentials.Certificate(valor)  # caminho do arquivo service-account.json
    else:
        cred = credentials.ApplicationDefault()  # Google Cloud / gcloud auth
    return firebase_admin.initialize_app(cred, options)


def get_firestore():
    return firestore.client(get_firebase_app())


def verify_id_token(token: str) -> dict:
    """Valida o token de login enviado pelo app (Firebase Auth)."""
    return auth.verify_id_token(token, app=get_firebase_app())
