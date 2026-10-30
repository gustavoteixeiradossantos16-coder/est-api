import { initializeApp } from 'firebase-admin/app';
import { FieldValue, getFirestore } from 'firebase-admin/firestore';
import { logger } from 'firebase-functions';
import { defineSecret, defineString } from 'firebase-functions/params';
import { setGlobalOptions } from 'firebase-functions/v2';
import { HttpsError, onCall, type CallableRequest } from 'firebase-functions/v2/https';

import { blockReason, MESSAGES_PER_DAY, MIN_SECONDS_BETWEEN_MINUTES, todayKey, usageToday, type UserProfile } from './plan';
import { callGemini, parseHistory } from './tutor';

initializeApp();
const db = getFirestore();

// São Paulo: mesma região configurada no app (FUNCTIONS_REGION)
setGlobalOptions({ region: 'southamerica-east1', maxInstances: 10 });

// firebase functions:secrets:set GEMINI_API_KEY
const geminiApiKey = defineSecret('GEMINI_API_KEY');
const geminiModel = defineString('GEMINI_MODEL', { default: 'gemini-3-flash-preview' });

function requireUid(request: CallableRequest): string {
  if (!request.auth) throw new HttpsError('unauthenticated', 'Faça login para continuar.');
  return request.auth.uid;
}

const userRef = (uid: string) => db.collection('users').doc(uid);

/**
 * Chamado pelo app a cada minuto de estudo com a tela aberta.
 * Substitui o protótipo, em que o navegador gravava minutesToday (e podia zerar o próprio limite).
 */
export const trackStudyMinute = onCall(async (request) => {
  const uid = requireUid(request);
  return db.runTransaction(async (tx) => {
    const snap = await tx.get(userRef(uid));
    if (!snap.exists) throw new HttpsError('failed-precondition', 'Perfil não encontrado.');
    const profile = snap.data() as UserProfile;
    const now = new Date();
    const { minutes, messages } = usageToday(profile, now);

    if (blockReason(profile, now)) return { minutesToday: minutes, blocked: true };

    // Evita que chamadas repetidas consumam ou "inflem" minutos
    const elapsed = (now.getTime() - (profile.lastMinuteAt ?? 0)) / 1000;
    if (elapsed < MIN_SECONDS_BETWEEN_MINUTES) return { minutesToday: minutes, blocked: false };

    const next = { studyDate: todayKey(now), minutesToday: minutes + 1, messagesToday: messages, lastMinuteAt: now.getTime() };
    tx.update(userRef(uid), next);
    return { minutesToday: next.minutesToday, blocked: blockReason({ ...profile, ...next }, now) !== null };
  });
});

/**
 * Tutor IA. A chave do Gemini fica só aqui (no protótipo ela ia no HTML e era pública).
 * Confere plano, dia de estudo, limite de minutos e teto diário de perguntas antes de chamar a IA.
 */
export const askTutor = onCall({ secrets: [geminiApiKey], timeoutSeconds: 60, memory: '256MiB' }, async (request) => {
  const uid = requireUid(request);
  const history = parseHistory(request.data);

  // Reserva a pergunta numa transação para dois envios simultâneos não furarem o teto
  const profile = await db.runTransaction(async (tx) => {
    const snap = await tx.get(userRef(uid));
    if (!snap.exists) throw new HttpsError('failed-precondition', 'Perfil não encontrado.');
    const current = snap.data() as UserProfile;
    const now = new Date();

    const reason = blockReason(current, now);
    if (reason === 'daily-limit') throw new HttpsError('resource-exhausted', 'Seu tempo de estudo de hoje acabou.');
    if (reason === 'not-study-day') throw new HttpsError('resource-exhausted', 'Hoje não é um dos seus dias de estudo.');

    const { minutes, messages } = usageToday(current, now);
    if (messages >= MESSAGES_PER_DAY[current.plan]) {
      throw new HttpsError('resource-exhausted', 'Você atingiu o limite de perguntas de hoje.');
    }
    tx.update(userRef(uid), { studyDate: todayKey(now), minutesToday: minutes, messagesToday: messages + 1 });
    return current;
  });

  try {
    const text = await callGemini({ apiKey: geminiApiKey.value(), model: geminiModel.value(), goal: profile.goal, history });
    return { text };
  } catch (error) {
    logger.error('Falha ao chamar o Gemini', { uid, error: String(error) });
    // Pergunta que não teve resposta não conta no limite do dia
    await userRef(uid).update({ messagesToday: FieldValue.increment(-1) }).catch(() => undefined);
    throw new HttpsError('unavailable', 'O tutor está indisponível no momento. Tente novamente.');
  }
});
