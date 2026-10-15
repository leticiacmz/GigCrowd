/*
  The festival page exists when - and only when - its identity is confirmed.

  Each case mirrors a real shape in the local catalogue: an event whose
  block states the series, a legacy festival date whose block was never
  written but whose own Songkick address states the series, and a plain
  concert whose address states none - for which the backend answers 404 and
  the link must not be rendered.
*/
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { festivalSeriesId } from './festivalIdentity.ts';

describe('festivalSeriesId', () => {
  it('reads the series id the stored block states', () => {
    assert.equal(
      festivalSeriesId({
        festival: {
          series_id: '1235',
          name: 'Lollapalooza 2027',
          url: 'https://www.songkick.com/festivals/1235-lollapalooza/id/43456089',
        },
      }),
      '1235',
    );
  });

  it('parses the series out of the block URL when no id was stored', () => {
    assert.equal(
      festivalSeriesId({
        festival: {
          url: 'https://www.songkick.com/festivals/387188-estereo-picnic/id/43456096',
        },
      }),
      '387188',
    );
  });

  it('falls back to the event address, which states the series itself', () => {
    // The legacy undated rows: no festival block was written beside them,
    // but the address the importer stored is the festival date's own.
    assert.equal(
      festivalSeriesId({
        festival: null,
        source: {
          url: 'https://www.songkick.com/festivals/1235-lollapalooza/id/40309526-lollapalooza-2022',
        },
      }),
      '1235',
    );
  });

  it('returns null for a concert, whose address states no series', () => {
    assert.equal(
      festivalSeriesId({
        festival: null,
        source: {
          url: 'https://www.songkick.com/concerts/43410955-charli-xcx-at-ziggo-dome',
        },
      }),
      null,
    );
  });

  it('returns null when the event carries nothing structured', () => {
    assert.equal(festivalSeriesId({}), null);
    assert.equal(
      festivalSeriesId({ festival: { name: 'Some Festival' } }),
      null,
    );
  });

  it('treats an empty series id as absent rather than as an identity', () => {
    assert.equal(
      festivalSeriesId({
        festival: {
          series_id: '   ',
          url: 'https://www.songkick.com/concerts/12345',
        },
      }),
      null,
    );
  });
});
