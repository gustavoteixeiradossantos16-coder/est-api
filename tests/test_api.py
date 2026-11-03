from __future__ import annotations

from fastapi.testclient import TestClient

from app import rules
from app.main import app


def gerar(client, **extra):
    body = {"concursoId": "ebserh", "concurso": "EBSERH", "cargo": "", "dias": ["qua", "seg"], "minutos": 30}
    body.update(extra)
    return client.post("/plano", json=body)


def test_health_sem_login():
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_rotas_exigem_login():
    r = TestClient(app).get("/me")
    assert r.status_code == 401
    assert r.json()["codigo"] == "NAO_AUTENTICADO"


def test_me_cria_perfil_free(client, store):
    r = client.get("/me").json()
    assert r["plan"] == "free" and r["dailyLimit"] == 30 and r["minutesToday"] == 0
    assert store.profiles["u1"]["email"] == "teste@exemplo.com"


def test_me_zera_minutos_quando_vira_o_dia(client, store):
    store.set_profile("u1", {"plan": "free", "studyDate": "2000-01-01", "minutesToday": 29})
    assert client.get("/me").json()["minutesToday"] == 0


def test_gerar_plano_aplica_limites_free_e_normaliza(client, store, ai):
    r = gerar(client, dias=["dom", "sab", "sex", "qua", "seg"], minutos=240)
    assert r.status_code == 200
    plano = r.json()["plano"]
    assert plano["dias"] == ["seg", "qua", "sex", "sab"]  # Free: máx. 4 dias, na ordem da semana
    assert plano["minutosDia"] == 30  # Free: 30 min/dia
    d = plano["dados"]
    assert [m["nome"] for m in d["materias"]] == ["Enfermagem", "Português"]  # ordenado por peso
    assert d["materias"][0]["peso"] == 100  # limitado a 0..100
    assert d["materias"][0]["assuntos"][0]["incidencia"] == "media"  # sem acento
    assert [c["dia"] for c in d["cronograma"]] == ["seg", "qua", "sex", "sab"]  # um item por dia
    assert d["cronograma"][0]["blocos"][1]["atividade"] == "teoria"  # atividade inválida vira teoria
    assert '"seg", "qua", "sex", "sab"' in ai.prompts[0] and "30 min por dia" in ai.prompts[0]
    assert isinstance(store.plans["u1"]["dados"], str)  # guardado como texto JSON (formato antigo)
    assert client.get("/plano").json()["plano"]["concurso"] == "EBSERH"


def test_pro_escolhe_dias_e_tempo(client, store):
    store.set_profile("u1", {"plan": "pro", "studyDate": rules.hoje(), "minutesToday": 0})
    plano = gerar(client, dias=["seg", "ter", "qua", "qui", "sex", "sab"], minutos=120).json()["plano"]
    assert len(plano["dias"]) == 6 and plano["minutosDia"] == 120


def test_progresso_valida_chave_e_salva(client):
    gerar(client)
    assert client.patch("/plano/progresso", json={"chave": "seg_0", "feito": True}).json()["progresso"]["itens"] == {"seg_0": True}
    assert client.patch("/plano/progresso", json={"chave": "seg_9", "feito": True}).status_code == 400
    assert client.patch("/plano/progresso", json={"chave": "__proto__", "feito": True}).status_code == 400
    assert client.get("/plano").json()["plano"]["progresso"]["itens"]["seg_0"] is True


def test_progresso_zera_na_semana_nova(client, store):
    gerar(client)
    store.update_plan("u1", {"progresso": {"semana": "2000-01-03", "itens": {"seg_0": True}}})
    assert client.get("/plano").json()["plano"]["progresso"]["itens"] == {}


def test_questoes_so_premium(client, store):
    gerar(client)
    r = client.post("/questoes", json={"materia": "Português"})
    assert r.status_code == 403 and r.json()["codigo"] == "PREMIUM"
    client.post("/me/upgrade")
    r = client.post("/questoes", json={"materia": "Português", "qtd": 5}).json()
    assert len(r["questoes"]) == 1  # descarta a questão sem gabarito válido
    assert r["questoes"][0]["correta"] == "A"


def test_anuncio_ate_4_por_dia(client):
    for i in range(4):
        r = client.post("/me/anuncio").json()
    assert r["bonusToday"] == 60 and r["dailyLimit"] == 90
    assert client.post("/me/anuncio").status_code == 429


def test_minutos_e_limite_do_chat(client, store):
    assert client.post("/chat", json={"mensagem": "oi"}).json()["resposta"] == "ok"
    store.update_profile("u1", {"minutesToday": 30})
    r = client.post("/chat", json={"mensagem": "oi"})
    assert r.status_code == 403 and r.json()["codigo"] == "LIMITE_DIARIO"


def test_minuto_nao_conta_duas_vezes_seguidas(client):
    client.get("/me")
    assert client.post("/me/minutos").json()["minutesToday"] == 1
    assert client.post("/me/minutos").json()["minutesToday"] == 1


def test_chat_estudo_monta_pedido_com_o_concurso(client, ai):
    gerar(client)
    r = client.post("/chat/estudo", json={"materia": "Português", "assunto": "Crase", "atividade": "revisao", "minutos": 15})
    msg = r.json()["mensagem"]
    assert "EBSERH (Técnico em Enfermagem)" in msg and "revisar Português, assunto: Crase" in msg
    assert "15 minutos" in msg and ai.chats[-1] == msg


def test_validacao_de_entrada(client):
    assert client.post("/plano", json={"concurso": "", "dias": []}).status_code == 422
    assert client.post("/chat/estudo", json={"materia": "x", "atividade": "hack"}).status_code == 422
