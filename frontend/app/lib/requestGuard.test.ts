/*
  Attendance belongs to the event that was explicitly confirmed, and the
  page must never present another event's answer as this one's.

  React keeps the event page mounted while its id changes, so a response
  for the previous event can arrive after the new page has started. These
  tests hold the two halves of the protection: the guard itself (only the
  newest request writes) and the wiring in the page file (both loaders
  claim through it, the page drops the previous event's state during
  render, and results of attendance/review actions are applied only while
  their event is still the one on screen).
*/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { createRequestGuard } from './requestGuard.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(here, '..', '..');

function read(relative: string): string {
  return readFileSync(path.join(frontendRoot, relative), 'utf8');
}

test('only the most recently started request may write its answer', () => {
  const guard = createRequestGuard();

  const first = guard.next();
  const second = guard.next();

  assert.equal(guard.isCurrent(first), false, 'the superseded request is stale');
  assert.equal(guard.isCurrent(second), true, 'the newest request is current');
});

test('a lost response leaves the guard without resurrecting older claims', () => {
  const guard = createRequestGuard();

  const first = guard.next();
  // The first request never answers; a later one starts and answers.
  const second = guard.next();

  assert.equal(guard.isCurrent(second), true);
  // The late first response must still be refused.
  assert.equal(guard.isCurrent(first), false);
});

test('guards of different loaders are independent', () => {
  const eventGuard = createRequestGuard();
  const showLogGuard = createRequestGuard();

  const eventToken = eventGuard.next();

  // The show-log loader claiming does not invalidate the event loader.
  showLogGuard.next();
  assert.equal(eventGuard.isCurrent(eventToken), true);
});

test('a response for a previous event never reaches the state of the current one', () => {
  // Mirrors the page's rule: claim at start, apply only while current.
  const guard = createRequestGuard();
  let shown: string | null = null;

  function startLoad() {
    return guard.next();
  }

  function respond(token: number, value: string) {
    if (guard.isCurrent(token)) shown = value;
  }

  const eventOne = startLoad();
  // The reader navigates: the new page's load starts before the old answers.
  const eventTwo = startLoad();
  respond(eventTwo, 'attendance of event two');
  respond(eventOne, 'attendance of event one');

  assert.equal(shown, 'attendance of event two');
});

test('the event page claims every load through a guard, for the id on screen', () => {
  const page = read('app/[locale]/events/[id]/page.tsx');

  assert.ok(
    page.includes('createRequestGuard'),
    'the page must import the request guard',
  );
  assert.ok(
    /const request = eventRequest\.next\(\)/.test(page),
    'loadEvent must claim a token before fetching',
  );
  assert.ok(
    /const request = showLogRequest\.next\(\)/.test(page),
    'loadShowLog must claim a token before fetching',
  );
  assert.ok(
    page.includes(
      'eventRequest.isCurrent(request) && pageEventId.current === target',
    ),
    'loadEvent must discard superseded answers and answers for another event',
  );
  assert.ok(
    page.includes(
      'showLogRequest.isCurrent(request) && pageEventId.current === target',
    ),
    'loadShowLog must discard superseded answers and answers for another event',
  );
  assert.ok(
    /const target = eventId;\s*\n\s*if \(pageEventId\.current !== target\) return;/.test(page),
    'a load started for another event id must refuse to compete at all',
  );
});

test('the event page drops the previous event state when its id changes', () => {
  const page = read('app/[locale]/events/[id]/page.tsx');

  assert.ok(
    /if \(renderedEventId !== eventId\) \{/.test(page),
    'the page must detect its own identity change during render',
  );

  const reset = page.slice(page.indexOf('if (renderedEventId !== eventId) {'));
  assert.ok(
    reset.includes('setShowLog(null);'),
    "the previous event's attendance must be dropped synchronously",
  );
  assert.ok(
    reset.includes('setEvent(null);'),
    "the previous event's record must not survive into the new page's frame",
  );
});

test('attendance and review results are applied only while their event is on screen', () => {
  const page = read('app/[locale]/events/[id]/page.tsx');

  // Every mutation result that writes state directly must pass the check.
  const directWrites = [
    'setShowLog(saved);',
    'setShowLog(cleared);',
  ];

  for (const write of directWrites) {
    const at = page.indexOf(write);
    assert.ok(at >= 0, `expected ${write} in the page`);
    const before = page.slice(Math.max(0, at - 400), at);
    assert.ok(
      before.includes('if (pageEventId.current !== eventId) return;'),
      `${write} must be preceded by the same-event check`,
    );
  }

  // The attendance action reloads state only for the event still displayed.
  const create = page.indexOf('await showLogAPI.create(');
  const afterCreate = page.slice(create, create + 600);
  assert.ok(
    afterCreate.includes('if (pageEventId.current !== eventId) return;'),
    'the create flow must stop applying results after navigation',
  );
});
