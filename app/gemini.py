"""Integração com a API Gemini: chat do Tutor, plano de estudos e questões.

Os prompts ficam só aqui no servidor; o app envia apenas os parâmetros.
O formato do JSON é garantido pelo schema (response_json_schema).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from .config import get_settings
from .errors import AppError, entrada_invalida
from .rules import ANOS_ANALISE, DIAS_NOME, agora, limpar

log = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """Você é um tutor especialista de concursos públicos do Brasil (StudyTimeIA).
Seja encorajador, direto, focado na banca organizadora (se informada) e use formatação limpa.
Evite textos muito longos, ensine usando tópicos ou metodologias ativas."""

MAX_HISTORICO = 40
MAX_TEXTO = 8000

# ---------------------------------------------------------------- schemas
STR = {"type": "string"}
NUM = {"type": "number"}


def _arr(items: dict) -> dict:
    return {"type": "array", "items": items}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props)}


SCHEMA_PLANO = _obj({
    "concurso": STR,
    "cargoConsiderado": STR,
    "bancas": _arr(STR),
    "periodo": STR,
    "provasAnalisadas": _arr(_obj({"ano": NUM, "banca": STR, "cargo": STR})),
    "resumo": STR,
    "materias": _arr(_obj({
        "nome": STR,
        "peso": NUM,
        "assuntos": _arr(_obj({"nome": STR, "incidencia": {"type": "string", "enum": ["alta", "media", "baixa"]}})),
    })),
    "tiposQuestao": _arr(_obj({"tipo": STR, "percentual": NUM, "dica": STR})),
    "cronograma": _arr(_obj({
        "dia": STR,
        "foco": STR,
        "blocos": _arr(_obj({
            "materia": STR, "assunto": STR, "minutos": NUM,
            "atividade": {"type": "string", "enum": ["teoria", "questoes", "revisao"]},
        })),
    })),
    "dicas": _arr(STR),
})

SCHEMA_QUESTOES = _obj({
    "questoes": _arr(_obj({
        "enunciado": STR,
        "alternativas": _arr(_obj({"letra": STR, "texto": STR})),
        "correta": STR,
        "explicacao": STR,
        "fonte": STR,
        "origem": {"type": "string", "enum": ["prova_anterior", "inedita"]},
    })),
})


# ---------------------------------------------------------------- prompts
def _periodo() -> tuple[int, int]:
    fim = agora().year
    return fim - ANOS_ANALISE + 1, fim


def prompt_plano(concurso: str, cargo: str, dias: list[str], minutos: int) -> str:
    concurso, cargo = limpar(concurso), limpar(cargo)
    if not concurso or not dias or not 0 < minutos <= 960:
        raise entrada_invalida("Dados do plano inválidos.")
    ini, fim = _periodo()
    cargo_txt = f', cargo "{cargo}"' if cargo else ""
    dias_txt = ", ".join(f'"{k}"' for k in dias)
    return (
        "Especialista em concursos públicos brasileiros.\n"
        f'1) Pesquise as provas de "{concurso}"{cargo_txt}, de {ini} a {fim} (bancas, editais, PCI, Qconcursos, Tec). '
        "Liste só provas realmente encontradas. Estime o peso (%) de cada matéria, os assuntos mais cobrados e os "
        'tipos de questão da banca. Sem cargo informado, use o de mais vagas em "cargoConsiderado".\n'
        f'2) Monte o cronograma semanal: dias {dias_txt} (use essas chaves em "dia"); {minutos} min por dia '
        "(soma exata dos blocos); blocos de 15 a 90 min; matérias proporcionais à incidência; intercale teoria, "
        "questões e revisão; assunto específico em cada bloco.\n"
        f'"periodo": "{ini}-{fim}". "resumo": 2 a 4 frases. "peso" e "percentual": 0 a 100.'
    )


def prompt_questoes(concurso: str, cargo: str, bancas: list[str], materia: str, assunto: str, qtd: int) -> str:
    concurso, cargo, materia, assunto = limpar(concurso), limpar(cargo), limpar(materia), limpar(assunto)
    bancas = [b for b in (limpar(b, 60) for b in bancas) if b][:5]
    qtd = min(max(int(qtd or 5), 1), 10)
    if not concurso or not materia:
        raise entrada_invalida("Dados das questões inválidos.")
    ini, fim = _periodo()
    cargo_txt = f', cargo "{cargo}"' if cargo else ""
    assunto_txt = f', assunto "{assunto}"' if assunto else ""
    return (
        f'Professor do concurso "{concurso}"{cargo_txt}; banca(s): {", ".join(bancas) or "não informada"}.\n'
        f'Traga {qtd} questões de provas de {ini} a {fim} sobre "{materia}"{assunto_txt}.\n'
        '- Prefira questões reais (origem "prova_anterior", fonte "Banca – Ano – Órgão – Cargo").\n'
        '- Se faltarem, crie inéditas no estilo da banca (origem "inedita", fonte "Inédita – estilo <banca>"). '
        "Nunca atribua inédita a prova real.\n"
        '- Mantenha o formato da banca (Cebraspe: letras "C" e "E").\n'
        '- "explicacao": por que a correta está certa e as outras erradas.'
    )


def mensagem_de_estudo(materia: str, assunto: str = "", atividade: str = "", minutos: int = 0,
                       concurso: str = "", cargo: str = "") -> str:
    """Pedido montado quando a pessoa clica em "Estudar com a IA" numa matéria do plano."""
    materia, assunto = limpar(materia), limpar(assunto, 160)
    concurso, cargo = limpar(concurso, 80), limpar(cargo, 80)
    if not materia:
        raise entrada_invalida("Informe a matéria.")
    tema = f"{materia}, assunto: {assunto}" if assunto else materia
    contexto = f"Estou estudando para o concurso {concurso}{f' ({cargo})' if cargo else ''}. " if concurso else ""
    if atividade == "questoes":
        pedido = (f"Quero praticar questões de {tema}, no estilo da banca do meu concurso. Me passe uma questão "
                  "de cada vez, espere minha resposta e depois corrija explicando cada alternativa.")
    elif atividade == "revisao":
        pedido = (f"Quero revisar {tema}. Faça uma revisão rápida com os pontos-chave, macetes e pegadinhas mais "
                  "comuns em prova e, no final, me faça 3 perguntas curtas para eu testar o que lembro.")
    else:
        pedido = (f"Quero estudar {tema}. Me explique a teoria de forma didática e passo a passo, destacando o "
                  "que mais cai em prova, com exemplos e um resumo no final.")
    tempo = f" Tenho cerca de {minutos} minutos para este bloco." if minutos and minutos > 0 else ""
    return contexto + pedido + tempo


# ---------------------------------------------------------------- serviço
class AIService(Protocol):
    def chat(self, mensagem: str, historico: list[dict]) -> dict[str, Any]: ...
    def gerar(self, prompt: str, schema: dict) -> dict[str, Any]: ...


def limpar_historico(historico: Any) -> list[dict]:
    """Aceita só mensagens {role: user|model, parts: [{text}]} e corta o tamanho."""
    limpo = []
    for item in historico if isinstance(historico, list) else []:
        if not isinstance(item, dict) or item.get("role") not in ("user", "model"):
            continue
        textos = [str(p.get("text", ""))[:MAX_TEXTO] for p in item.get("parts") or [] if isinstance(p, dict)]
        textos = [t for t in textos if t]
        if textos:
            limpo.append({"role": item["role"], "parts": [{"text": t} for t in textos]})
    return limpo[-MAX_HISTORICO:]


def _traduzir_erro(e: genai_errors.APIError) -> AppError:
    if e.code == 429:
        if "PerDay" in str(e) or "per day" in str(e):
            return AppError(429, "COTA_DIARIA", "O limite diário da IA foi atingido. Tente novamente mais tarde.")
        return AppError(429, "COTA", "Muitas solicitações agora. Aguarde um minuto e tente de novo.")
    if e.code == 400:
        return AppError(400, "ENTRADA_INVALIDA", "Requisição inválida para a IA.")
    return AppError(502, "IA_INDISPONIVEL", "Não foi possível falar com a IA. Tente novamente.")


class GeminiService:
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise AppError(503, "SEM_CHAVE", "A IA não está configurada no servidor (GEMINI_API_KEY).")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def chat(self, mensagem: str, historico: list[dict]) -> dict[str, Any]:
        texto = (mensagem or "").strip()[:MAX_TEXTO]
        if not texto:
            raise entrada_invalida("Mensagem vazia.")
        contents = limpar_historico(historico) + [{"role": "user", "parts": [{"text": texto}]}]
        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION),
            )
        except genai_errors.APIError as e:
            log.warning("[Gemini chat] %s", e)
            raise _traduzir_erro(e) from e
        resposta = resp.text or ""
        if not resposta:
            raise AppError(502, "IA_INDISPONIVEL", "A IA não retornou nenhuma resposta.")
        return {"resposta": resposta, "historico": contents + [{"role": "model", "parts": [{"text": resposta}]}]}

    def gerar(self, prompt: str, schema: dict) -> dict[str, Any]:
        """Uma única chamada com pesquisa no Google e JSON garantido pelo schema."""

        def chamar(com_pesquisa: bool):
            texto = prompt if com_pesquisa else (
                prompt + "\nSem acesso à web: use seu conhecimento e cite apenas provas de que tem certeza.")
            return self.client.models.generate_content(
                model=self.model,
                contents=[{"role": "user", "parts": [{"text": texto}]}],
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())] if com_pesquisa else None,
                    response_mime_type="application/json",
                    response_json_schema=schema,
                    thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
                ),
            )

        try:
            try:
                resp = chamar(True)
            except genai_errors.APIError as e:
                # A pesquisa no Google tem cota própria: se esgotou, gera sem pesquisa.
                if e.code != 429:
                    raise
                log.warning("[Gemini] Cota da pesquisa no Google esgotada; gerando sem pesquisa.")
                resp = chamar(False)
        except genai_errors.APIError as e:
            log.warning("[Gemini gerar] %s", e)
            raise _traduzir_erro(e) from e

        try:
            dados = json.loads(resp.text or "")
        except ValueError as e:
            raise AppError(502, "PARSE", "A IA retornou uma resposta inválida. Tente novamente.") from e

        fontes, vistos = [], set()
        try:
            chunks = resp.candidates[0].grounding_metadata.grounding_chunks or []
        except (AttributeError, IndexError, TypeError):
            chunks = []
        for c in chunks:
            web = getattr(c, "web", None)
            uri = getattr(web, "uri", None) or ""
            if not re.match(r"^https?://", uri):
                continue
            titulo = getattr(web, "title", None) or uri
            if titulo not in vistos:
                vistos.add(titulo)
                fontes.append({"titulo": titulo, "url": uri})
        return {"json": dados, "fontes": fontes}


_service: GeminiService | None = None


def get_ai() -> AIService:
    global _service
    if _service is None:
        s = get_settings()
        _service = GeminiService(s.gemini_api_key, s.gemini_model)
    return _service


__all__ = [
    "AIService", "GeminiService", "get_ai", "SCHEMA_PLANO", "SCHEMA_QUESTOES",
    "prompt_plano", "prompt_questoes", "mensagem_de_estudo", "limpar_historico", "DIAS_NOME",
]
