/*
  The two festival addresses, told apart by shape and never by lookup.

  A festival is addressed by one of its dates (`/festivals/{eventId}`) or by
  the series it is (`/festivals/series/{seriesId}`), and both reach the same
  page. These tests pin what keeps that from going wrong: the parameter rules
  that decide which route a value belongs to, the canonical link shape the
  event page hands out - which the browser verification follows end to end -
  and the edition parameter the series page opens on.

  As with the other presentation tests, there is no React harness here: the
  files that ship are read and their decisions are pinned as files. Live
  navigation remains the browser check.
*/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import {
  festivalEditionFromSearch,
  festivalSeriesHref,
  resolveFestivalSeriesParam,
} from './festivalSeries.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(here, '..', '..');

function read(relative: string): string {
  return readFileSync(path.join(frontendRoot, relative), 'utf8');
}

test('a numeric parameter names a series, an object id names a date', () => {
  assert.deepEqual(resolveFestivalSeriesParam('3441108'), {
    kind: 'series',
    seriesId: '3441108',
  });

  // The one value shape both addresses could hold. A 24-character hex id is
  // an event's own id - Songkick's series ids are far shorter - so it goes to
  // the date-keyed route rather than being read as a series that cannot
  // exist.
  assert.deepEqual(
    resolveFestivalSeriesParam('507f1f77bcf86cd799439011'),
    { kind: 'legacy-event', eventId: '507f1f77bcf86cd799439011' },
  );

  // An all-digit object id is still an object id.
  assert.deepEqual(
    resolveFestivalSeriesParam('123456789012345678901234'),
    { kind: 'legacy-event', eventId: '123456789012345678901234' },
  );
});

test('a parameter that is neither shape names no festival', () => {
  assert.deepEqual(resolveFestivalSeriesParam('../events'), {
    kind: 'invalid',
  });
  assert.deepEqual(resolveFestivalSeriesParam(''), {
    kind: 'invalid',
  });
  assert.deepEqual(resolveFestivalSeriesParam(undefined), {
    kind: 'invalid',
  });
});

test('the canonical festival link keeps every festival address shape', () => {
  const href = festivalSeriesHref('pt-BR', '3441108', 'abc');

  // The journey the browser verification follows: every festival link on an
  // event page starts with this prefix, and the page it opens is the
  // festival's own - series id in the path, the arriving date as the edition
  // to open on.
  assert.ok(
    href.startsWith('/pt-BR/festivals/'),
    'a festival link must stay under the localized festival path',
  );
  assert.equal(
    href,
    '/pt-BR/festivals/series/3441108?edition=abc',
  );
});

test('the edition is read from the query only when it names an event', () => {
  const id = '507f1f77bcf86cd799439011';

  assert.equal(
    festivalEditionFromSearch(`?edition=${id}`),
    id,
  );
  assert.equal(
    festivalEditionFromSearch(`?page=2&edition=${id}&x=1`),
    id,
  );

  // Anything that is not a stored event's own id is dropped, so a crafted
  // query string never becomes a question about a record that cannot exist.
  assert.equal(festivalEditionFromSearch('?edition=../../etc'), null);
  assert.equal(festivalEditionFromSearch('?edition='), null);
  assert.equal(festivalEditionFromSearch('?page=2'), null);
});

test('the festival view carries the response lineup state', () => {
  const view = read('components/festival/FestivalDetails.tsx');

  assert.ok(
    view.includes("data-lineup-state={festival.lineup_state ?? 'unknown'}"),
    'the lineup section must carry whether the lineup is held, so an ' +
      'unheld lineup is never presented as an empty bill',
  );
});
