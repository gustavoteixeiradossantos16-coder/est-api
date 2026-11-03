"""API do StudyTimeIA.

Rotas (todas, menos /health, exigem `Authorization: Bearer <idToken do Firebase>`):

  GET   /health                 status da API
  GET   /me                     perfil + limites do dia
  POST  /me/minutos             soma 1 minuto de estudo (plano Free)
  POST  /me/anuncio             recompensa do anúncio (+15 min, até 4 por dia)
  POST  /me/upgrade             ativa o Premium (simulado, sem pagamento)
  GET   /plano                  plano de estudos salvo (ou null)
  POST  /plano                  gera um novo plano com a IA e salva
  PATCH /plano/progresso        marca/desmarca um bloco do cronograma
  POST  /questoes               questões de provas anteriores (Premium)
  POST  /chat                   conversa com o Tutor IA
  POST  /chat/estudo            abre o Tutor já estudando uma matéria do plano
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import rules
from .auth import CurrentUser, get_current_user
from .config import get_settings
from .errors import AppError
from .gemini import (SCHEMA_PLANO, SCHEMA_QUESTOES, AIService, get_ai, mensagem_de_estudo, prompt_plano,
                     prompt_questoes, texto_puro)
from .store import FirestoreStore, Store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("studytimeia")

app = FastAPI(title="StudyTimeIA API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(AppError)
async def _app_error(_: Request, e: AppError):
    return JSONResponse(status_code=e.status, content={"erro": e.mensagem, "codigo": e.codigo})


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, e: RequestValidationError):
    return JSONResponse(status_code=422, content={"erro": "Dados inválidos.", "codigo": "ENTRADA_INVALIDA",
                                                  "detalhes": e.errors()[:5]})


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = FirestoreStore(get_settings().app_id)
    return _store


# ---------------------------------------------------------------- modelos de entrada
class ChatIn(BaseModel):
    mensagem: str = Field(min_length=1, max_length=8000)
    historico: list[dict[str, Any]] = Field(default_factory=list)


class EstudoIn(BaseModel):
    materia: str = Field(min_length=1, max_length=120)
    assunto: str = Field(default="", max_length=160)
    atividade: str = Field(default="teoria", pattern="^(teoria|questoes|revisao)$")
    minutos: int = Field(default=0, ge=0, le=960)


class PlanoIn(BaseModel):
    concursoId: str | None = Field(default=None, max_length=40)
    concurso: str = Field(min_length=2, max_length=80)
    cargo: str = Field(default="", max_length=80)
    dias: list[str] = Field(min_length=1, max_length=7)
    minutos: int = Field(default=rules.FREE_MINUTES, ge=15, le=960)


class ProgressoIn(BaseModel):
    chave: str = Field(max_length=10)
    feito: bool


class QuestoesIn(BaseModel):
    materia: str = Field(min_length=1, max_length=120)
    assunto: str = Field(default="", max_length=120)
    qtd: int = Field(default=5, ge=1, le=10)


# ---------------------------------------------------------------- helpers
def carregar_perfil(store: Store, user: CurrentUser) -> dict[str, Any]:
    """Lê o perfil; cria se não existir e zera os minutos quando vira o dia."""
    perfil = store.get_profile(user.uid)
    if perfil is None:
        perfil = rules.perfil_novo(user.email)
        store.set_profile(user.uid, perfil)
        return perfil
    mudancas = rules.virar_o_dia(perfil)
    if mudancas:
        store.update_profile(user.uid, mudancas)
    return perfil


def carregar_plano(store: Store, uid: str) -> dict[str, Any] | None:
    """Lê o plano; o progresso é semanal e zera quando começa uma nova semana."""
    plano = rules.plano_do_banco(store.get_plan(uid))
    if plano and plano["progresso"].get("semana") != rules.inicio_da_semana():
        plano["progresso"] = {"semana": rules.inicio_da_semana(), "itens": {}}
        store.update_plan(uid, {"progresso": plano["progresso"]})
    return plano


def exigir_plano(store: Store, uid: str) -> dict[str, Any]:
    plano = carregar_plano(store, uid)
    if not plano:
        raise AppError(404, "SEM_PLANO", "Você ainda não tem um plano de estudos.")
    return plano


# Trava: cada pessoa só pode ter UMA geração (plano/questões) em andamento por vez
_gerando: set[str] = set()
_gerando_lock = threading.Lock()


class _UmaGeracao:
    def __init__(self, uid: str):
        self.uid = uid

    def __enter__(self):
        with _gerando_lock:
            if self.uid in _gerando:
                raise AppError(409, "OCUPADO", "Já existe uma geração em andamento. Aguarde terminar.")
            _gerando.add(self.uid)

    def __exit__(self, *exc):
        with _gerando_lock:
            _gerando.discard(self.uid)


# ---------------------------------------------------------------- rotas
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me")
def me(user: CurrentUser = Depends(get_current_user), store: Store = Depends(get_store)):
    return rules.resumo_perfil(carregar_perfil(store, user))


@app.post("/me/minutos")
def somar_minuto(user: CurrentUser = Depends(get_current_user), store: Store = Depends(get_store)):
    """Chamado pelo app a cada minuto de estudo no Tutor (só conta no plano Free)."""
    perfil = carregar_perfil(store, user)
    if not rules.is_pro(perfil) and not rules.atingiu_limite(perfil):
        agora = datetime.now(timezone.utc)
        ultimo = perfil.get("lastMinuteAt")
        # ignora chamadas repetidas em menos de 45s (evita contar o mesmo minuto duas vezes)
        if not ultimo or (agora - datetime.fromisoformat(ultimo)).total_seconds() >= 45:
            perfil["minutesToday"] = int(perfil.get("minutesToday") or 0) + 1
            perfil["lastMinuteAt"] = agora.isoformat()
            store.update_profile(user.uid, {"minutesToday": perfil["minutesToday"],
                                            "lastMinuteAt": perfil["lastMinuteAt"]})
    return rules.resumo_perfil(perfil)


@app.post("/me/anuncio")
def recompensa_anuncio(user: CurrentUser = Depends(get_current_user), store: Store = Depends(get_store)):
    perfil = carregar_perfil(store, user)
    if rules.is_pro(perfil):
        raise AppError(400, "JA_PRO", "No Premium o tempo de estudo já é ilimitado.")
    if rules.anuncios_hoje(perfil) >= rules.AD_MAX_PER_DAY:
        raise AppError(429, "LIMITE_ANUNCIOS",
                       f"Você já usou os {rules.AD_MAX_PER_DAY} anúncios de hoje. Volte amanhã ou faça upgrade.")
    mudancas = {"bonusDate": rules.hoje(), "bonusMinutes": rules.bonus_hoje(perfil) + rules.AD_BONUS}
    perfil.update(mudancas)
    store.update_profile(user.uid, mudancas)
    return rules.resumo_perfil(perfil)


@app.post("/me/upgrade")
def upgrade(user: CurrentUser = Depends(get_current_user), store: Store = Depends(get_store)):
    if not get_settings().allow_fake_upgrade:
        raise AppError(403, "PAGAMENTO_NECESSARIO", "O pagamento ainda não está disponível.")
    perfil = carregar_perfil(store, user)
    perfil["plan"] = "pro"
    store.update_profile(user.uid, {"plan": "pro"})
    return rules.resumo_perfil(perfil)


@app.get("/plano")
def obter_plano(user: CurrentUser = Depends(get_current_user), store: Store = Depends(get_store)):
    return {"plano": carregar_plano(store, user.uid)}


@app.post("/plano")
def gerar_plano(body: PlanoIn, user: CurrentUser = Depends(get_current_user),
                store: Store = Depends(get_store), ai: AIService = Depends(get_ai)):
    perfil = carregar_perfil(store, user)
    dias, minutos = rules.escolhas_do_plano(perfil, body.dias, body.minutos)
    concurso, cargo = rules.limpar(body.concurso, 80), rules.limpar(body.cargo, 80)
    with _UmaGeracao(user.uid):
        resultado = ai.gerar(prompt_plano(concurso, cargo, dias, minutos), SCHEMA_PLANO)
    dados = rules.normalizar_plano(resultado["json"], dias)
    fontes = resultado["fontes"][:15]
    registro = {
        "concursoId": body.concursoId, "concurso": concurso, "cargo": cargo,
        "dias": dias, "minutosDia": minutos,
        "progresso": {"semana": rules.inicio_da_semana(), "itens": {}},
        # "dados" e "fontes" ficam como texto JSON, no mesmo formato do site antigo
        "dados": json.dumps(dados, ensure_ascii=False),
        "fontes": json.dumps(fontes, ensure_ascii=False),
        "criadoEm": datetime.now(timezone.utc),
    }
    store.set_plan(user.uid, registro)
    return {"plano": rules.plano_do_banco(registro)}


@app.patch("/plano/progresso")
def marcar_progresso(body: ProgressoIn, user: CurrentUser = Depends(get_current_user),
                     store: Store = Depends(get_store)):
    plano = exigir_plano(store, user.uid)
    if not rules.chave_bloco_valida(plano, body.chave):
        raise AppError(400, "ENTRADA_INVALIDA", "Bloco do cronograma inválido.")
    plano["progresso"]["itens"][body.chave] = body.feito
    store.update_plan(user.uid, {f"progresso.itens.{body.chave}": body.feito})
    return {"progresso": plano["progresso"]}


@app.post("/questoes")
def gerar_questoes(body: QuestoesIn, user: CurrentUser = Depends(get_current_user),
                   store: Store = Depends(get_store), ai: AIService = Depends(get_ai)):
    perfil = carregar_perfil(store, user)
    if not rules.is_pro(perfil):
        raise AppError(403, "PREMIUM", "As questões de provas anteriores são exclusivas do Premium.")
    plano = exigir_plano(store, user.uid)
    d = plano["dados"]
    with _UmaGeracao(user.uid):
        resultado = ai.gerar(
            prompt_questoes(plano["concurso"], d.get("cargoConsiderado") or plano.get("cargo", ""),
                            d.get("bancas", []), body.materia, body.assunto, body.qtd),
            SCHEMA_QUESTOES,
        )
    questoes = []
    for q in resultado["json"].get("questoes") or []:
        alts = [a for a in (q.get("alternativas") or []) if isinstance(a, dict) and a.get("texto")]
        correta = str(q.get("correta", "")).upper()
        if q.get("enunciado") and len(alts) >= 2 and any(str(a.get("letra", "")).upper() == correta for a in alts):
            questoes.append({
                **q,
                "correta": correta,
                "enunciado": texto_puro(str(q["enunciado"])),
                "explicacao": texto_puro(str(q.get("explicacao") or "")),
                "alternativas": [{"letra": str(a["letra"]).upper(), "texto": texto_puro(str(a["texto"]))} for a in alts],
            })
    if not questoes:
        raise AppError(502, "PARSE", "A IA retornou uma resposta inválida. Tente novamente.")
    return {"questoes": questoes, "materia": body.materia}


def _checar_limite_chat(perfil: dict[str, Any]) -> None:
    if rules.atingiu_limite(perfil):
        raise AppError(403, "LIMITE_DIARIO",
                       "Você atingiu o limite de estudo de hoje. Assista a um anúncio ou faça upgrade.")


@app.post("/chat")
def chat(body: ChatIn, user: CurrentUser = Depends(get_current_user),
         store: Store = Depends(get_store), ai: AIService = Depends(get_ai)):
    _checar_limite_chat(carregar_perfil(store, user))
    return ai.chat(body.mensagem, body.historico)


@app.post("/chat/estudo")
def chat_estudo(body: EstudoIn, user: CurrentUser = Depends(get_current_user),
                store: Store = Depends(get_store), ai: AIService = Depends(get_ai)):
    """Botão "Estudar com a IA": o servidor monta o pedido a partir da matéria do plano."""
    _checar_limite_chat(carregar_perfil(store, user))
    plano = carregar_plano(store, user.uid)
    concurso = plano["concurso"] if plano else ""
    cargo = (plano["dados"].get("cargoConsiderado") or plano.get("cargo", "")) if plano else ""
    mensagem = mensagem_de_estudo(body.materia, body.assunto, body.atividade, body.minutos, concurso, cargo)
    return {"mensagem": mensagem, **ai.chat(mensagem, [])}
