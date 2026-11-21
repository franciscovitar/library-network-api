import test from 'node:test';
import assert from 'node:assert/strict';
import { apply, availableActions, initialState } from './model.js';

const step = (s, a) => apply(s, { type: a });

test('only one synthetic request is accepted and the other gets 409', () => {
  const s = step(initialState(), 'RACE');
  assert.equal(s.loan.borrower, 'Norte');
  assert.equal(s.copy, 'RESERVED');
  assert.equal(s.log[0].code, '409');
  assert.equal(Object.keys(s.requestKeys).length, 1);
});

test('idempotency retry has no new loan and changed payload is blocked', () => {
  const s = step(initialState(), 'RACE');
  const retry = step(s, 'RETRY');
  assert.equal(retry.log[0].code, '200');
  assert.deepEqual(retry.loan, s.loan);
  const alt = step(retry, 'ALTER');
  assert.equal(alt.log[0].code, '409');
});

test('outbound and return must traverse every state before release', () => {
  let s = step(initialState(), 'RACE');
  assert.equal(availableActions(s).activate, false);
  for (let i = 0; i < 3; i++) s = step(s, 'ADVANCE');
  assert.equal(s.location, 'Norte');
  assert.equal(s.loan.status, 'REQUESTED');
  s = step(s, 'ACTIVATE');
  s = apply(s, { type: 'RETURN', condition: 'GOOD' });
  assert.equal(s.copy, 'PENDING_RETURN');
  for (let i = 0; i < 3; i++) s = step(s, 'ADVANCE');
  assert.deepEqual([s.copy,s.location,s.loan.status], ['AVAILABLE','Central','CLOSED']);
});

test('damaged copy is retired and cannot be reserved again', () => {
  let s = step(initialState(), 'RACE');
  for (let i = 0; i < 3; i++) s = step(s, 'ADVANCE');
  s = step(s, 'ACTIVATE');
  s = apply(s, { type: 'RETURN', condition: 'DAMAGED' });
  for (let i = 0; i < 3; i++) s = step(s, 'ADVANCE');
  assert.equal(s.copy, 'RETIRED');
  assert.equal(apply(s,{type:'REQUEST',member:'Sur',key:'new'}).log[0].code, '409');
});

test('a healthy copy can start a second cycle with a new idempotency key', () => {
  let s = step(initialState(),'RACE');
  for(let i=0;i<3;i++) s=step(s,'ADVANCE');
  s=step(s,'ACTIVATE');s=apply(s,{type:'RETURN',condition:'GOOD'});
  for(let i=0;i<3;i++) s=step(s,'ADVANCE');
  s=step(s,'RACE');
  assert.equal(s.loan.status,'REQUESTED');
  assert.equal(s.raceSequence,2);
  assert.equal(Object.keys(s.requestKeys).length,2);
});

test('illegal transition does not change domain state', () => {
  let s = step(initialState(), 'INVALID');
  assert.equal(s.log[0].code, '409');
  assert.equal(s.copy, 'AVAILABLE');
  s = step(s, 'RESET');
  assert.equal(s.step, 0);
});
