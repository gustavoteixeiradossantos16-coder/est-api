"""Fixtures: API com Firestore em memória, IA falsa e login simulado (sem rede)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.gemini import get_ai
from app.main import app, get_store
from app.store import MemoryStore

PLANO_IA = {
    "concurso": "EBSERH", "cargoConsiderado": "Técnico em Enfermagem", "bancas": ["IBFC"], "periodo": "2012-2026",
    "provasAnalisadas": [{"ano": 2023, "banca": "IBFC", "cargo": "Téc. Enfermagem"}],
    "resumo": "Foque em SUS.",
    "materias": [
        {"nome": "Português", "peso": 20, "assuntos": [{"nome": "Interpretação", "incidencia": "alta"}]},
        {"nome": "Enfermagem", "peso": 150, "assuntos": [{"nome": "Sinais vitais", "incidencia": "média"}]},
    ],
    "tiposQuestao": [{"tipo": "Múltipla escolha", "percentual": 100, "dica": "Leia tudo."}],
    "cronograma": [
        {"dia": "seg", "foco": "SUS", "blocos": [
            {"materia": "Enfermagem", "assunto": "Sinais vitais", "minutos": 20, "atividade": "teoria"},
            {"materia": "Português", "assunto": "Interpretação", "minutos": 10, "atividade": "xyz"},
        ]},
        {"dia": "Quarta", "foco": "", "blocos": []},
    ],
    "dicas": ["Resolva questões"],
}

QUESTOES_IA = {"questoes": [
    {"enunciado": "2+2?", "alternativas": [{"letra": "a", "texto": "4"}, {"letra": "b", "texto": "5"}],
     "correta": "a", "explicacao": "Soma.", "fonte": "IBFC – 2023", "origem": "prova_anterior"},
    {"enunciado": "sem gabarito", "alternativas": [{"letra": "A", "texto": "x"}, {"letra": "B", "texto": "y"}],
     "correta": "Z", "explicacao": "", "fonte": "", "origem": "inedita"},
]}


class FakeAI:
    def __init__(self):
        self.prompts: list[str] = []
        self.chats: list[str] = []

    def gerar(self, prompt, schema):
        self.prompts.append(prompt)
        return {"json": QUESTOES_IA if "questões" in prompt.split("\n")[1] else PLANO_IA,
                "fontes": [{"titulo": "PCI", "url": "https://pci.example"}]}

    def chat(self, mensagem, historico):
        self.chats.append(mensagem)
        return {"resposta": "ok", "historico": historico + [{"role": "user", "parts": [{"text": mensagem}]}]}


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def ai():
    return FakeAI()


@pytest.fixture
def client(store, ai):
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_ai] = lambda: ai
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(uid="u1", email="teste@exemplo.com")
    yield TestClient(app)
    app.dependency_overrides.clear()
