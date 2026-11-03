"""Regras de negócio dos planos Free e Premium (antes ficavam só no navegador)."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .config import get_settings
from .errors import AppError, entrada_invalida

FREE_MAX_DAYS = 4
FREE_MINUTES = 30
AD_BONUS = 15  # minutos ganhos por anúncio
AD_MAX_PER_DAY = 4  # até +60 min/dia
ANOS_ANALISE = 15
DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
DIAS_NOME = {
    "seg": "Segunda", "ter": "Terça", "qua": "Quarta", "qui": "Quinta",
    "sex": "Sexta", "sab": "Sábado", "dom": "Domingo",
}
ATIVIDADES = {"teoria", "questoes", "revisao"}
INCIDENCIAS = {"alta", "media", "baixa"}


# ---------------------------------------------------------------- datas
def agora() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone))


def hoje() -> str:
    return agora().date().isoformat()


def inicio_da_semana(d: date | None = None) -> str:
    d = d or agora().date()
    return (d - timedelta(days=d.weekday())).isoformat()  # segunda-feira


# ---------------------------------------------------------------- perfil
def is_pro(perfil: dict[str, Any]) -> bool:
    return perfil.get("plan") == "pro"


def perfil_novo(email: str | None) -> dict[str, Any]:
    return {"email": email or "", "plan": "free", "studyDate": hoje(), "minutesToday": 0}


def virar_o_dia(perfil: dict[str, Any]) -> dict[str, Any]:
    """Zera o contador de minutos quando muda o dia. Devolve os campos alterados."""
    if perfil.get("studyDate") != hoje():
        mudancas = {"studyDate": hoje(), "minutesToday": 0}
        perfil.update(mudancas)
        return mudancas
    return {}


def bonus_hoje(perfil: dict[str, Any]) -> int:
    return int(perfil.get("bonusMinutes") or 0) if perfil.get("bonusDate") == hoje() else 0


def anuncios_hoje(perfil: dict[str, Any]) -> int:
    return round(bonus_hoje(perfil) / AD_BONUS)


def limite_diario(perfil: dict[str, Any]) -> int | None:
    """Minutos de estudo permitidos hoje (None = ilimitado no Premium)."""
    return None if is_pro(perfil) else FREE_MINUTES + bonus_hoje(perfil)


def atingiu_limite(perfil: dict[str, Any]) -> bool:
    limite = limite_diario(perfil)
    return limite is not None and int(perfil.get("minutesToday") or 0) >= limite


def resumo_perfil(perfil: dict[str, Any]) -> dict[str, Any]:
    """Perfil + números prontos para a tela."""
    return {
        "email": perfil.get("email", ""),
        "plan": "pro" if is_pro(perfil) else "free",
        "minutesToday": int(perfil.get("minutesToday") or 0),
        "dailyLimit": limite_diario(perfil),
        "bonusToday": bonus_hoje(perfil),
        "adsToday": anuncios_hoje(perfil),
        "adMaxPerDay": AD_MAX_PER_DAY,
        "adBonus": AD_BONUS,
        "freeMaxDays": FREE_MAX_DAYS,
        "freeMinutes": FREE_MINUTES,
        "limitReached": atingiu_limite(perfil),
    }


# ---------------------------------------------------------------- textos
def limpar(valor: Any, maximo: int = 120) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()[:maximo]


def ordenar_dias(dias: list[str]) -> list[str]:
    return [k for k in DIAS if k in set(dias)]


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def _pct(n: Any) -> float:
    try:
        return max(0.0, min(100.0, float(n)))
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------- plano
def escolhas_do_plano(perfil: dict[str, Any], dias: list[str], minutos: int) -> tuple[list[str], int]:
    """Aplica os limites do plano Free às escolhas da pessoa."""
    dias = ordenar_dias([d for d in dias if d in DIAS_NOME])
    if not dias:
        raise entrada_invalida("Escolha pelo menos um dia da semana.")
    if is_pro(perfil):
        if not 15 <= minutos <= 960:
            raise entrada_invalida("Escolha entre 15 minutos e 16 horas por dia.")
        return dias, minutos
    return dias[:FREE_MAX_DAYS], FREE_MINUTES


def normalizar_plano(dados: dict[str, Any], dias: list[str]) -> dict[str, Any]:
    """Limpa a resposta da IA e garante um item de cronograma para cada dia escolhido."""
    materias = []
    for m in dados.get("materias") or []:
        if not isinstance(m, dict) or not m.get("nome"):
            continue
        assuntos = []
        for a in m.get("assuntos") or []:
            if isinstance(a, dict) and a.get("nome"):
                inc = _sem_acento(str(a.get("incidencia") or "baixa"))
                assuntos.append({"nome": str(a["nome"]), "incidencia": inc if inc in INCIDENCIAS else "baixa"})
        materias.append({"nome": str(m["nome"]), "peso": _pct(m.get("peso")), "assuntos": assuntos})
    materias.sort(key=lambda m: m["peso"], reverse=True)

    crono_ia = [c for c in (dados.get("cronograma") or []) if isinstance(c, dict)]
    cronograma = []
    for k in dias:
        item = next((c for c in crono_ia if str(c.get("dia", "")).lower().startswith(k)), {})
        blocos = []
        for b in item.get("blocos") or []:
            if isinstance(b, dict) and b.get("materia"):
                atividade = b.get("atividade") if b.get("atividade") in ATIVIDADES else "teoria"
                blocos.append({
                    "materia": str(b["materia"]),
                    "assunto": str(b.get("assunto") or ""),
                    "minutos": max(0, round(float(b.get("minutos") or 0))),
                    "atividade": atividade,
                })
        cronograma.append({"dia": k, "foco": str(item.get("foco") or ""), "blocos": blocos})

    if not materias or all(not d["blocos"] for d in cronograma):
        raise AppError(502, "PARSE", "A IA retornou uma resposta inválida. Tente novamente.")

    def _lista_str(v: Any) -> list[str]:
        return [str(x) for x in (v or []) if x]

    return {
        "concurso": str(dados.get("concurso") or ""),
        "cargoConsiderado": str(dados.get("cargoConsiderado") or ""),
        "bancas": _lista_str(dados.get("bancas")),
        "periodo": str(dados.get("periodo") or ""),
        "provasAnalisadas": [p for p in (dados.get("provasAnalisadas") or []) if isinstance(p, dict)],
        "resumo": str(dados.get("resumo") or ""),
        "materias": materias,
        "tiposQuestao": [
            {"tipo": str(t["tipo"]), "percentual": _pct(t.get("percentual")), "dica": str(t.get("dica") or "")}
            for t in (dados.get("tiposQuestao") or []) if isinstance(t, dict) and t.get("tipo")
        ],
        "cronograma": cronograma,
        "dicas": _lista_str(dados.get("dicas")),
    }


def plano_do_banco(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Converte o documento do Firestore (dados guardados como texto JSON) para a API."""
    if not doc:
        return None
    try:
        dados = json.loads(doc["dados"]) if isinstance(doc.get("dados"), str) else doc.get("dados")
        fontes = json.loads(doc.get("fontes") or "[]") if isinstance(doc.get("fontes"), str) else (doc.get("fontes") or [])
    except (ValueError, KeyError):
        return None
    if not isinstance(dados, dict):
        return None
    criado = doc.get("criadoEm")
    return {
        "concursoId": doc.get("concursoId"),
        "concurso": doc.get("concurso", ""),
        "cargo": doc.get("cargo", ""),
        "dias": doc.get("dias", []),
        "minutosDia": doc.get("minutosDia", FREE_MINUTES),
        "progresso": doc.get("progresso") or {"semana": inicio_da_semana(), "itens": {}},
        "dados": dados,
        "fontes": fontes,
        "criadoEm": criado.isoformat() if hasattr(criado, "isoformat") else criado,
    }


def chave_bloco_valida(plano: dict[str, Any], chave: str) -> bool:
    """A chave do progresso é "<dia>_<índice do bloco>" e precisa existir no cronograma."""
    m = re.fullmatch(r"(seg|ter|qua|qui|sex|sab|dom)_(\d{1,2})", chave or "")
    if not m:
        return False
    dia = next((d for d in plano["dados"]["cronograma"] if d["dia"] == m.group(1)), None)
    return bool(dia) and int(m.group(2)) < len(dia["blocos"])
