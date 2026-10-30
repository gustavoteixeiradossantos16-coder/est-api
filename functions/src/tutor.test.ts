import assert from 'node:assert/strict';
import { test } from 'node:test';

import { MAX_HISTORY, parseHistory } from './tutor';

test('aceita conversa válida', () => {
  const history = [
    { role: 'user', text: 'O que é ato administrativo?' },
    { role: 'model', text: 'É...' },
    { role: 'user', text: 'E os atributos?' },
  ];
  assert.equal(parseHistory({ history }).length, 3);
});

test('rejeita formatos inválidos', () => {
  assert.throws(() => parseHistory(null));
  assert.throws(() => parseHistory({ history: [] }));
  assert.throws(() => parseHistory({ history: [{ role: 'system', text: 'oi' }] }));
  assert.throws(() => parseHistory({ history: [{ role: 'model', text: 'oi' }] }));
  assert.throws(() => parseHistory({ history: [{ role: 'user', text: 'x'.repeat(2001) }] }));
  const tooLong = Array.from({ length: MAX_HISTORY + 1 }, () => ({ role: 'user', text: 'oi' }));
  assert.throws(() => parseHistory({ history: tooLong }));
});
