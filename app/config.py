"""Configuração lida das variáveis de ambiente (arquivo .env no desenvolvimento)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _lista(valor: str) -> list[str]:
    return [v.strip() for v in valor.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    # Conta de serviço do Firebase: JSON inteiro (bom para Vercel) ou caminho do arquivo
    firebase_service_account: str
    firebase_project_id: str
    # Pasta raiz dos dados no Firestore (mesma usada pelo site antigo)
    app_id: str
    cors_origins: list[str]
    # Upgrade simulado (sem pagamento real). Desligue em produção quando houver Stripe.
    allow_fake_upgrade: bool
    timezone: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
        firebase_service_account=os.getenv(
            "FIREBASE_SERVICE_ACCOUNT", str(BASE_DIR / "service-account.json")
        ),
        firebase_project_id=os.getenv("FIREBASE_PROJECT_ID", "studytimeia"),
        app_id=os.getenv("APP_ID", "concursa-ia-local-app"),
        cors_origins=_lista(
            os.getenv("CORS_ORIGINS", "http://localhost:8081,http://localhost:19006")
        ),
        allow_fake_upgrade=os.getenv("ALLOW_FAKE_UPGRADE", "true").lower() == "true",
        timezone=os.getenv("APP_TIMEZONE", "America/Sao_Paulo"),
    )
