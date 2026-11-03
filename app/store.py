"""Acesso aos dados de cada usuário no Firestore.

Usa os mesmos caminhos do site antigo, então as contas e planos existentes continuam valendo:
  artifacts/{APP_ID}/users/{uid}/profile/main
  artifacts/{APP_ID}/users/{uid}/studyPlan/current
"""
from __future__ import annotations

import copy
from typing import Any, Protocol

from .firebase import get_firestore


class Store(Protocol):
    def get_profile(self, uid: str) -> dict[str, Any] | None: ...
    def set_profile(self, uid: str, data: dict[str, Any]) -> None: ...
    def update_profile(self, uid: str, fields: dict[str, Any]) -> None: ...
    def get_plan(self, uid: str) -> dict[str, Any] | None: ...
    def set_plan(self, uid: str, data: dict[str, Any]) -> None: ...
    def update_plan(self, uid: str, fields: dict[str, Any]) -> None: ...


class FirestoreStore:
    def __init__(self, app_id: str):
        self.app_id = app_id

    def _user(self, uid: str):
        return get_firestore().collection("artifacts").document(self.app_id).collection("users").document(uid)

    def _profile(self, uid: str):
        return self._user(uid).collection("profile").document("main")

    def _plan(self, uid: str):
        return self._user(uid).collection("studyPlan").document("current")

    def get_profile(self, uid):
        snap = self._profile(uid).get()
        return snap.to_dict() if snap.exists else None

    def set_profile(self, uid, data):
        self._profile(uid).set(data)

    def update_profile(self, uid, fields):
        self._profile(uid).update(fields)

    def get_plan(self, uid):
        snap = self._plan(uid).get()
        return snap.to_dict() if snap.exists else None

    def set_plan(self, uid, data):
        self._plan(uid).set(data)

    def update_plan(self, uid, fields):
        self._plan(uid).update(fields)


class MemoryStore:
    """Armazenamento em memória (testes e desenvolvimento sem Firebase)."""

    def __init__(self):
        self.profiles: dict[str, dict[str, Any]] = {}
        self.plans: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _apply(doc: dict[str, Any], fields: dict[str, Any]) -> None:
        for chave, valor in fields.items():
            alvo = doc
            partes = chave.split(".")  # suporta "progresso.itens.seg_0" como no Firestore
            for p in partes[:-1]:
                alvo = alvo.setdefault(p, {})
            alvo[partes[-1]] = valor

    def get_profile(self, uid):
        return copy.deepcopy(self.profiles.get(uid))

    def set_profile(self, uid, data):
        self.profiles[uid] = copy.deepcopy(data)

    def update_profile(self, uid, fields):
        self._apply(self.profiles.setdefault(uid, {}), fields)

    def get_plan(self, uid):
        return copy.deepcopy(self.plans.get(uid))

    def set_plan(self, uid, data):
        self.plans[uid] = copy.deepcopy(data)

    def update_plan(self, uid, fields):
        self._apply(self.plans.setdefault(uid, {}), fields)
