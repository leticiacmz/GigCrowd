/*
  Regression tests for the festival title presentation rules.

  Run with: npm test  (node --test, no framework needed)

  Every example here maps to a real shape the local database holds: an
  artist-prefixed title, an edition named "Festival @ Venue", festival names
  with years and subtitles, and events whose only name is their title.
*/
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  eventDisplayTitle,
  festivalDisplayName,
  stripArtistPrefix,
} from './festivalTitle.ts';

test('the artist is never shown twice in the header', () => {
  // The pre-fix header for this shape read
  // "Demi Lovato @ Demi Lovato Rock In Rio 2022".
  assert.equal(
    eventDisplayTitle({
      festivalName: null,
      title: 'Demi Lovato Rock In Rio 2022',
      artistName: 'Demi Lovato',
    }),
    'Demi Lovato @ Rock In Rio 2022',
  );

  // A stored festival name taken from the artist's own appearance page
  // names the performance, not the festival: it is refused, and the
  // header falls back to the title's festival part.
  assert.equal(
    eventDisplayTitle({
      festivalName: 'Demi Lovato @ Barra Olympic Park',
      title: 'Demi Lovato Rock In Rio 2022',
      artistName: 'Demi Lovato',
    }),
    'Demi Lovato @ Rock In Rio 2022',
  );
});

test('legitimate festival names stay intact', () => {
  assert.equal(
    eventDisplayTitle({
      festivalName: 'Rock The Mountain 2026',
      title: 'Some Artist Rock The Mountain 2026',
      artistName: 'Some Artist',
    }),
    'Some Artist @ Rock The Mountain 2026',
  );

  assert.equal(
    festivalDisplayName({
      festivalName: 'Rock The Mountain 2026',
      title: 'Whatever The Listing Called It',
    }),
    'Rock The Mountain 2026',
  );

  assert.equal(
    eventDisplayTitle({
      festivalName: 'Meli Music 2026',
      title: 'Meli Music 2026',
      artistName: 'Luan Santana',
    }),
    'Luan Santana @ Meli Music 2026',
  );

  assert.equal(
    festivalDisplayName({ festivalName: 'Meli Music 2026' }),
    'Meli Music 2026',
  );
});

test('a "Festival @ Venue" name keeps its venue and gains no second "@"', () => {
  assert.equal(
    eventDisplayTitle({
      festivalName: 'Rock In Rio 2022 @ Barra Olympic Park',
      title: 'Demi Lovato Rock In Rio 2022',
      artistName: 'Demi Lovato',
    }),
    'Rock In Rio 2022 @ Barra Olympic Park',
  );

  // Without an artist to consider, the stored name is the header, verbatim.
  assert.equal(
    eventDisplayTitle({
      festivalName: 'Kiss 108\'s Jingle Ball 2022 @ TD Garden',
      title: 'irrelevant',
    }),
    'Kiss 108\'s Jingle Ball 2022 @ TD Garden',
  );
});

test('a title with no festival metadata still has a valid fallback', () => {
  // No festival block, no artist: the stored title is shown as it is.
  assert.equal(
    eventDisplayTitle({ festivalName: null, title: 'Just A Show 2026' }),
    'Just A Show 2026',
  );

  // A title that is nothing but the artist's name yields the artist alone.
  assert.equal(
    eventDisplayTitle({
      festivalName: null,
      title: 'Demi Lovato',
      artistName: 'Demi Lovato',
    }),
    'Demi Lovato',
  );

  // Nothing at all: empty string, never "undefined".
  assert.equal(eventDisplayTitle({}), '');
});

test('the stored name is returned verbatim, never rewritten', () => {
  const source = {
    festivalName: '  Rock In Rio 2022 @ Barra Olympic Park  ',
    title: 'Demi Lovato Rock In Rio 2022',
    artistName: 'Demi Lovato',
  };

  const before = { ...source };

  assert.equal(
    festivalDisplayName(source),
    'Rock In Rio 2022 @ Barra Olympic Park',
  );
  assert.equal(
    eventDisplayTitle(source),
    'Rock In Rio 2022 @ Barra Olympic Park',
  );

  // The presentation layer reads its inputs; it never mutates them.
  assert.deepEqual(source, before);
});

test('the artist prefix is stripped only from the front of a title', () => {
  assert.equal(
    stripArtistPrefix('Demi Lovato Rock In Rio 2022', 'Demi Lovato'),
    'Rock In Rio 2022',
  );

  assert.equal(
    stripArtistPrefix('Rock In Rio feat. Demi Lovato', 'Demi Lovato'),
    'Rock In Rio feat. Demi Lovato',
  );

  // Case-insensitive at the front, and an exact-match title strips away.
  assert.equal(
    stripArtistPrefix('demi lovato', 'Demi Lovato'),
    '',
  );

  assert.equal(stripArtistPrefix(null, 'Demi Lovato'), '');
  assert.equal(stripArtistPrefix('Only A Title', null), 'Only A Title');
});

test('the stored festival name wins over the artist-prefixed title', () => {
  assert.equal(
    festivalDisplayName({
      festivalName: 'Festival HERA HSBC 2024 @ Autódromo Hermanos Rodríguez',
      title: 'Demi Lovato Festival HERA HSBC 2024',
      artistName: 'Demi Lovato',
    }),
    'Festival HERA HSBC 2024 @ Autódromo Hermanos Rodríguez',
  );

  // With no stored name, the stripped title is the fallback.
  assert.equal(
    festivalDisplayName({
      festivalName: null,
      title: 'Demi Lovato Festival HERA HSBC 2024',
      artistName: 'Demi Lovato',
    }),
    'Festival HERA HSBC 2024',
  );
});

test('a stored name beginning with the artist names the appearance, not the festival', () => {
  // Songkick's artist pages embed a microformat naming the date after the
  // performer; an import that read it stored exactly that as the festival's
  // name. It must never be displayed as the festival.
  const source = {
    festivalName: 'Charli XCX @ Autódromo José Carlos Pace (Interlagos)',
    title: 'Charli XCX @ Autódromo José Carlos Pace (Interlagos)',
    artistName: 'Charli XCX',
  };

  // The card shows the venue descriptor rather than the artist as festival.
  assert.equal(
    festivalDisplayName(source),
    'Autódromo José Carlos Pace (Interlagos)',
  );

  // The header still reads as the artist at that place.
  assert.equal(
    eventDisplayTitle(source),
    'Charli XCX @ Autódromo José Carlos Pace (Interlagos)',
  );
});

test('the official edition name that merely shares a word with the artist is kept', () => {
  assert.equal(
    festivalDisplayName({
      festivalName: 'Lollapalooza 2027 @ Autódromo José Carlos Pace',
      title: 'Charli XCX @ Autódromo José Carlos Pace (Interlagos)',
      artistName: 'Charli XCX',
    }),
    'Lollapalooza 2027 @ Autódromo José Carlos Pace',
  );
});

test('stripping the artist also drops the "@" it leaves behind', () => {
  assert.equal(
    stripArtistPrefix('Charli XCX @ Zilker Park', 'Charli XCX'),
    'Zilker Park',
  );

  assert.equal(
    stripArtistPrefix('Charli XCX@Zilker Park', 'Charli XCX'),
    'Zilker Park',
  );
});
