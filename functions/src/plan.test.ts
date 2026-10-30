import assert from 'node:assert/strict';
import { test } from 'node:test';

import { blockReason, todayDay, todayKey, usageToday, type UserProfile } from './plan';

// 2026-11-02 é uma segunda-feira
const mondayNoonBrasilia = new Date('2026-11-02T15:00:00Z');
const mondayLateNightBrasilia = new Date('2026-11-03T01:30:00Z'); // 22:30 de segunda em Brasília

const base: UserProfile = {
  email: 'a@b.com',
  plan: 'free',
  goal: 'TRT',
  studyDays: ['seg', 'qua'],
  studyDate: '2026-11-02',
  minutesToday: 10,
};

test('o dia vira à meia-noite de Brasília, não à meia-noite UTC', () => {
  assert.equal(todayKey(mondayLateNightBrasilia), '2026-11-02');
  assert.equal(todayDay(mondayLateNightBrasilia), 'seg');
});

test('contadores de outro dia contam como zero', () => {
  assert.deepEqual(usageToday({ ...base, studyDate: '2026-11-01' }, mondayNoonBrasilia), { minutes: 0, messages: 0 });
});

test('plano gratuito bloqueia ao chegar em 30 minutos', () => {
  assert.equal(blockReason(base, mondayNoonBrasilia), null);
  assert.equal(blockReason({ ...base, minutesToday: 30 }, mondayNoonBrasilia), 'daily-limit');
});

test('plano gratuito bloqueia fora dos dias escolhidos', () => {
  assert.equal(blockReason({ ...base, studyDays: ['ter'] }, mondayNoonBrasilia), 'not-study-day');
});

test('plano pro nunca bloqueia', () => {
  assert.equal(blockReason({ ...base, plan: 'pro', studyDays: [], minutesToday: 999 }, mondayNoonBrasilia), null);
});
