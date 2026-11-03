# est-api

Back-end do **StudyTimeIA** em Python ([FastAPI](https://fastapi.tiangolo.com/)).

Ele concentra tudo o que não pode ficar no navegador/celular:

- **IA (Gemini)** — chat do Tutor, geração do plano de estudos e das questões. A chave fica só no servidor.
- **Dados (Firestore)** — perfil, plano e progresso de cada pessoa, via Firebase Admin.
- **Regras dos planos** — limite do Free (4 dias, 30 min/dia, até 4 anúncios de +15 min) e recursos do Premium.
- **Tutor em texto puro** — o System Prompt exige respostas sem Markdown, conversa guiada (saudações e
  perguntas gerais: 2–3 frases + opções numeradas) e explicação completa passo a passo para pedidos diretos.
  Como rede de segurança, `texto_puro()` remove qualquer marcação que escape (asteriscos, #, crases, blocos de código).
- **Login** — toda rota confere o token do Firebase Auth enviado pelo app ([est-web](https://github.com/gustavoteixeiradossantos16-coder/est-web)).

Os dados continuam nos mesmos caminhos do site antigo (`artifacts/{APP_ID}/users/{uid}/...`),
então as contas e planos existentes continuam valendo.

## Rodando localmente

Requer **Python 3.13** (o 3.15 ainda não tem todas as bibliotecas).

```bash
py -3.13 -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements-dev.txt
copy .env.example .env            # e preencha GEMINI_API_KEY
# coloque o service-account.json do Firebase na raiz (ele é ignorado pelo git)
uvicorn app.main:app --reload --port 8000
```

- Documentação interativa: http://localhost:8000/docs
- Testes (sem rede, com IA e banco simulados): `pytest`

## Rotas

Todas, menos `/health`, exigem `Authorization: Bearer <idToken do Firebase>`.
Erros sempre voltam como `{"erro": "mensagem para a pessoa", "codigo": "CODIGO"}`.

| Método | Rota | O que faz |
|---|---|---|
| GET | `/health` | Status da API |
| GET | `/me` | Perfil + limites do dia (`dailyLimit`, `minutesToday`, `adsToday`…) |
| POST | `/me/minutos` | Soma 1 minuto de estudo no Tutor (plano Free) |
| POST | `/me/anuncio` | Recompensa do anúncio: +15 min (até 4 por dia) |
| POST | `/me/upgrade` | Ativa o Premium (**simulado**, ver `ALLOW_FAKE_UPGRADE`) |
| GET | `/plano` | Plano salvo (ou `null`) |
| POST | `/plano` | Gera o plano com a IA e salva |
| PATCH | `/plano/progresso` | Marca/desmarca um bloco (`{"chave": "seg_0", "feito": true}`) |
| POST | `/questoes` | Questões de provas anteriores (Premium) |
| POST | `/chat` | Conversa com o Tutor |
| POST | `/chat/estudo` | Botão "Estudar com a IA": o servidor monta o pedido a partir da matéria |

Códigos úteis para o front: `NAO_AUTENTICADO` (401), `LIMITE_DIARIO` e `PREMIUM` (403), `OCUPADO` (409),
`COTA` / `COTA_DIARIA` / `LIMITE_ANUNCIOS` (429), `PARSE` (502), `SEM_CHAVE` (503).

## Deploy na Vercel

O `vercel.json` aponta para `app/main.py` com até 90 s por requisição (a geração do plano leva até ~1 min).
Em **Settings → Environment Variables** configure:

| Variável | Valor |
|---|---|
| `GEMINI_API_KEY` | chave da API Gemini |
| `FIREBASE_SERVICE_ACCOUNT` | o **conteúdo** do `service-account.json` (JSON em uma linha) |
| `CORS_ORIGINS` | endereço do est-web publicado (ex.: `https://est-web.vercel.app`) |
| `ALLOW_FAKE_UPGRADE` | `false` quando houver pagamento real |

> ⚠️ A cota **gratuita** do Gemini é de 20 pedidos por dia por modelo — não é suficiente para produção.
> Ative o faturamento no Google AI Studio antes de abrir para o público.

## Estrutura

```
app/
  main.py      rotas e modelos de entrada
  rules.py     regras dos planos, datas e normalização do plano gerado
  gemini.py    prompts, schemas e chamadas à IA
  store.py     Firestore (produção) e memória (testes)
  auth.py      validação do token do Firebase
  firebase.py  inicialização do Firebase Admin
  config.py    variáveis de ambiente
tests/         testes com pytest
```

## Fluxo de branches

- `main`: produção (padrão)
- `develop`: desenvolvimento (base das features)
- `qas`: homologação (recebe da develop)

Trabalhe em branches `feature/*` a partir da `develop` e abra PRs pequenos para a `develop`.
