# est-api

Back-end do **StudyTimeIA** no Firebase (projeto `studytimeia`): Cloud Functions em TypeScript (Node.js 22) e regras do Firestore. O app fica no repositório [est-web](https://github.com/gustavoteixeiradossantos16-coder/est-web).

Fluxo de branches:

- `main`: produção (padrão)
- `develop`: desenvolvimento (base das features)
- `qas`: homologação (recebe da develop)

Trabalhe em branches `feature/*` a partir da `develop` e abra PRs pequenos para a `develop`.

## O que tem aqui

| Caminho | O que faz |
|---|---|
| `functions/src/index.ts` | `askTutor`: recebe a conversa, confere plano e limites, chama o Gemini e devolve a resposta. `trackStudyMinute`: registra cada minuto de estudo e diz se o aluno foi bloqueado. |
| `functions/src/plan.ts` | Regras de plano: 30 min/dia e até 4 dias/semana no gratuito, teto de perguntas por dia e o dia virando à meia-noite de Brasília. |
| `functions/src/tutor.ts` | Validação da conversa enviada pelo app e chamada ao Gemini (a chave fica no servidor). |
| `firestore.rules` | O usuário só lê o próprio `users/{uid}` e só altera foco e dias de estudo. Plano e contadores ficam só com o servidor. |
| `tests/` | Testes das regras e um teste de ponta a ponta das funções, ambos no emulador. |

Modelo de dados (`users/{uid}`):

```ts
{
  email: string;
  plan: 'free' | 'pro';          // só o servidor muda
  goal: string | null;           // foco de estudo (onboarding)
  studyDays: ('dom'|'seg'|'ter'|'qua'|'qui'|'sex'|'sab')[];
  studyDate: 'YYYY-MM-DD';       // dia (Brasília) dos contadores abaixo
  minutesToday: number;          // só o servidor muda
  messagesToday?: number;        // só o servidor muda
  lastMinuteAt?: number;         // só o servidor muda
}
```

## Rodando localmente

Pré-requisitos: Node.js 22, Java 11+ (para os emuladores) e `npm i -g firebase-tools`.

```bash
cd functions && npm install && npm test        # testes da lógica de plano e validação
cd ../tests && npm install && npm test         # testes das regras do Firestore no emulador
echo "GEMINI_API_KEY=sua-chave" > functions/.secret.local   # opcional, para o tutor responder no emulador
npm run e2e                                    # (dentro de tests/) funções + auth + firestore no emulador
```

## Publicando no projeto `studytimeia`

1. Ative o plano **Blaze** (pago por uso). Cloud Functions e segredos exigem ele, mas o volume inicial cabe na cota gratuita.
2. `firebase login` e confira com `firebase use studytimeia`.
3. Guarde a chave do Gemini como segredo (ela nunca vai para o app):
   ```bash
   firebase functions:secrets:set GEMINI_API_KEY
   ```
4. Publique as regras e as funções:
   ```bash
   firebase deploy --only firestore:rules,functions
   ```
5. Para trocar o modelo do Gemini sem mexer no código, defina `GEMINI_MODEL` em `functions/.env.studytimeia` (padrão: `gemini-3-flash-preview`, o mesmo do protótipo).

> As regras hoje publicadas no projeto estão **abertas**: num teste, a coleção de usuários foi listada sem login. Publique o `firestore.rules` deste repositório antes de divulgar o app.

## Sugestões para o back-end

**Fazer antes de lançar**

1. **Pagamento de verdade.** O protótipo virava Premium com um clique, sem cobrar. Recomendo o Mercado Pago (Pix e cartão, comum no Brasil) ou o Stripe (extensão "Run Payments with Stripe"). O fluxo é: o app abre o checkout, o webhook confirma o pagamento numa Cloud Function e só essa função grava `plan: 'pro'`. Cancelamento e inadimplência voltam para `free` pelo mesmo webhook. Use só o webhook como fonte da verdade e nunca o retorno do app.
2. **Firebase App Check** (Play Integrity no Android, App Attest no iOS e reCAPTCHA na web), com `enforceAppCheck: true` nas funções. Isso impede que scripts usem a sua cota do Gemini fingindo ser o app.
3. **Orçamento e alertas** no Google Cloud Billing e na API do Gemini. Cada pergunta tem custo, e os tetos de `MESSAGES_PER_DAY` em `plan.ts` são o segundo freio.
4. **LGPD.** Escreva a política de privacidade e os termos. Ofereça exclusão de conta: uma função que apaga `users/{uid}` e o usuário no Auth (as lojas de apps exigem isso). Avise que as perguntas passam pelo Google Gemini.
5. **Verificação de e-mail** no cadastro (`sendEmailVerification`) e login com Google, para reduzir contas falsas que reiniciam o plano gratuito.

**Próximos passos**

6. **Histórico de conversas** em `users/{uid}/chats/{chatId}/messages`, gravado pela função `askTutor`. O Premium promete "histórico ilimitado", e hoje o chat some ao fechar o app.
7. **Relatórios.** Um registro diário em `users/{uid}/days/{YYYY-MM-DD}` (minutos e perguntas) alimenta o menu "Relatórios" do protótipo sem consultas caras.
8. **Respostas em streaming.** `onCall` já suporta streaming e deixa o tutor mais rápido de perceber.
9. **Observabilidade.** Os logs estruturados já saem no Cloud Logging. Crie alertas para a taxa de erro do `askTutor` e ligue o Crashlytics no app.
10. **CI no GitHub Actions.** `npm test` em `functions/` e `tests/` a cada PR. O deploy automático vai para um projeto `studytimeia-qas` a partir da branch `qas` e para `studytimeia` a partir da `main`. Separe os projetos Firebase por ambiente, porque hoje existe só o de produção.
11. **Plano anual e cupons** com o mesmo webhook. Ficam simples de fazer quando o pagamento existir.
