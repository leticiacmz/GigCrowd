/*
  The register flow, as pure logic and as the files that ship.

  Registering ends with a session, the same one a login produces: the
  response is stored whole, an answer without a token is a visible failure,
  and the page is closed to visitors who already have a session. Errors are
  shown as what the backend said, or as the page's own sentence when the
  backend said something that is not a sentence (a 422's array of error
  objects).

  The unit cases cover the message helper directly; the file pins hold the
  pages to the rules a file read can hold - everything else about these
  pages is browser behavior, checked by hand.
*/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { apiErrorMessage } from './apiError.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(here, '..', '..');

function read(relative: string): string {
  return readFileSync(path.join(frontendRoot, relative), 'utf8');
}

test('an auth failure shows the backend sentence, or the page fallback', () => {
  // FastAPI's handled failures carry a string detail.
  assert.equal(
    apiErrorMessage(
      { response: { data: { detail: 'Email already registered' } } },
      'fallback',
    ),
    'Email already registered',
  );

  // Its 422s carry an array of error objects, which is not a message.
  assert.equal(
    apiErrorMessage(
      {
        response: {
          data: {
            detail: [
              {
                loc: ['body', 'email'],
                msg: 'value is not a valid email address',
              },
            ],
          },
        },
      },
      'fallback',
    ),
    'fallback',
  );

  // A request that never got an answer has no detail at all.
  assert.equal(apiErrorMessage(new Error('Network Error'), 'fallback'), 'fallback');
  assert.equal(apiErrorMessage(undefined, 'fallback'), 'fallback');
  assert.equal(apiErrorMessage(null, 'fallback'), 'fallback');

  // An empty or whitespace-only detail is not a message either.
  assert.equal(
    apiErrorMessage({ response: { data: { detail: '   ' } } }, 'fallback'),
    'fallback',
  );

  // A detail that is a sentence is trimmed before it is shown.
  assert.equal(
    apiErrorMessage(
      { response: { data: { detail: '  Email already registered  ' } } },
      'fallback',
    ),
    'Email already registered',
  );
});

test('the register page stores the session the route returns', () => {
  const page = read('app/[locale]/register/page.tsx');

  // The response is a session - token plus user - and it is stored whole,
  // through the same mechanism login uses. An answer without a token is a
  // visible failure, never a silently broken session.
  assert.ok(page.includes('if (!response?.access_token)'));
  assert.ok(page.includes('saveAuth(response)'));

  // Errors go through the shared reader, not through a raw detail access
  // that would put a 422's array where a sentence belongs.
  assert.ok(page.includes('apiErrorMessage(err, t('));
  assert.ok(!page.includes('err.response?.data?.detail'));
});

test('the register page is closed to a session that already exists', () => {
  const page = read('app/[locale]/register/page.tsx');

  // No frame shows the form before the session question is answered.
  assert.ok(page.includes('if (!sessionChecked)'));
  assert.ok(page.includes("from '../../../components/LoadingState'"));

  // An authenticated visitor is sent on, honoring `next` like login does.
  assert.ok(page.includes('isAuthenticated()'));
  assert.ok(page.includes('getNextParam()'));
  assert.ok(page.includes('router.replace('));

  // And the check re-runs when the session changes, so signing out in
  // another tab returns the form instead of stranding this one.
  assert.ok(page.includes("addEventListener('auth-changed', evaluate)"));
});

test('the login page reads its errors the same way the register page does', () => {
  const page = read('app/[locale]/login/page.tsx');

  assert.ok(page.includes('apiErrorMessage(err, t('));
  assert.ok(!page.includes('err.response?.data?.detail'));
});
