/*
  Regression tests for the editions country filter.

  Run with: npm test  (node --test, no framework needed)

  The examples mirror the local catalogue: a series with editions across
  several countries, editions whose country was never recorded, and the
  single-country case where the filter has nothing to narrow.
*/
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  ALL_COUNTRIES,
  editionCountries,
  editionCountry,
  matchesCountry,
} from './festivalEditions.ts';

test('the edition’s own country wins, the venue is the fallback', () => {
  assert.equal(
    editionCountry({
      location: { country: 'Brazil' },
      venue: { country: 'Argentina' },
    }),
    'Brazil',
  );

  assert.equal(
    editionCountry({ location: null, venue: { country: 'Chile' } }),
    'Chile',
  );
});

test('a country that was never recorded is not invented', () => {
  assert.equal(editionCountry({}), null);
  assert.equal(editionCountry({ location: {}, venue: {} }), null);
  assert.equal(editionCountry({ location: { country: '  ' } }), null);
});

test('the options are exactly the countries the editions state', () => {
  const editions = [
    { location: { country: 'Brazil' } },
    { location: { country: 'Argentina' } },
    { location: { country: 'Brazil' }, venue: { country: 'France' } },
    { location: null },
  ];

  assert.deepEqual(editionCountries(editions), [
    'Argentina',
    'Brazil',
  ]);
});

test('a single-country series offers no choice to make', () => {
  const editions = [
    { location: { country: 'Brazil' } },
    { location: { country: 'Brazil' } },
  ];

  assert.deepEqual(editionCountries(editions), ['Brazil']);
});

test('all keeps every edition, including the ones with no country', () => {
  const unknown = { location: null, venue: null };

  assert.equal(matchesCountry(unknown, ALL_COUNTRIES), true);
  assert.equal(
    matchesCountry({ location: { country: 'France' } }, ALL_COUNTRIES),
    true,
  );
});

test('a selected country keeps only its editions', () => {
  const brazil = { location: { country: 'Brazil' } };
  const france = { location: { country: 'France' } };
  const unknown = { location: null, venue: null };

  assert.equal(matchesCountry(brazil, 'Brazil'), true);
  assert.equal(matchesCountry(france, 'Brazil'), false);

  // An edition with no recorded country does not appear under a specific
  // country: the filter must not guess where it took place.
  assert.equal(matchesCountry(unknown, 'Brazil'), false);
});
