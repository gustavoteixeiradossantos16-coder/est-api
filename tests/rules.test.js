import { assertFails, assertSucceeds, initializeTestEnvironment } from '@firebase/rules-unit-testing';
import { doc, getDoc, setDoc, updateDoc } from 'firebase/firestore';
import { readFileSync } from 'node:fs';
import { after, before, beforeEach, test } from 'node:test';

let env;

const newProfile = (email) => ({
  email,
  plan: 'free',
  goal: null,
  studyDays: [],
  studyDate: '2026-11-02',
  minutesToday: 0,
});

before(async () => {
  env = await initializeTestEnvironment({
    projectId: 'demo-studytimeia',
    firestore: { rules: readFileSync(new URL('../firestore.rules', import.meta.url), 'utf8') },
  });
});

beforeEach(async () => {
  await env.clearFirestore();
  // Perfil existente da Ana, gravado "pelo servidor" (sem regras)
  await env.withSecurityRulesDisabled((ctx) => setDoc(doc(ctx.firestore(), 'users/ana'), newProfile('ana@x.com')));
});

after(() => env.cleanup());

const asAna = () => env.authenticatedContext('ana', { email: 'ana@x.com' }).firestore();

test('visitante sem login não lê nada', async () => {
  const db = env.unauthenticatedContext().firestore();
  await assertFails(getDoc(doc(db, 'users/ana')));
  await assertFails(getDoc(doc(db, 'artifacts/concursa-ia-local-app/users/ana')));
});

test('usuário lê só o próprio perfil', async () => {
  await assertSucceeds(getDoc(doc(asAna(), 'users/ana')));
  const bia = env.authenticatedContext('bia', { email: 'bia@x.com' }).firestore();
  await assertFails(getDoc(doc(bia, 'users/ana')));
});

test('cadastro cria perfil gratuito zerado, e não pro', async () => {
  const bia = env.authenticatedContext('bia', { email: 'bia@x.com' }).firestore();
  await assertFails(setDoc(doc(bia, 'users/bia'), { ...newProfile('bia@x.com'), plan: 'pro' }));
  await assertFails(setDoc(doc(bia, 'users/bia'), { ...newProfile('bia@x.com'), minutesToday: -100 }));
  await assertFails(setDoc(doc(bia, 'users/bia'), newProfile('outra@x.com')));
  await assertSucceeds(setDoc(doc(bia, 'users/bia'), newProfile('bia@x.com')));
});

test('onboarding altera foco e dias (até 4 no gratuito)', async () => {
  const db = asAna();
  await assertSucceeds(updateDoc(doc(db, 'users/ana'), { goal: 'TRT 2', studyDays: ['seg', 'qua', 'sex', 'sab'] }));
  await assertFails(updateDoc(doc(db, 'users/ana'), { goal: 'TRT 2', studyDays: ['seg', 'ter', 'qua', 'qui', 'sex'] }));
  await assertFails(updateDoc(doc(db, 'users/ana'), { goal: '', studyDays: ['seg'] }));
  await assertFails(updateDoc(doc(db, 'users/ana'), { goal: 'TRT', studyDays: ['feriado'] }));
});

test('usuário não muda plano nem minutos (golpe do Premium grátis do protótipo)', async () => {
  const db = asAna();
  await assertFails(updateDoc(doc(db, 'users/ana'), { plan: 'pro' }));
  await assertFails(updateDoc(doc(db, 'users/ana'), { minutesToday: 0, studyDate: '2099-01-01' }));
});
