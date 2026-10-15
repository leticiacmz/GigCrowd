/*
  Opening an artist from a lineup, as pure logic over injected calls.

  Every case here maps to a rule the product relies on: an existing artist
  is reused, an unimported one is imported by Songkick id, repeated clicks
  share one operation, and an entry with no safe identity fails instead of
  being matched by name. The gateway calls are injected, so nothing here
  touches the network, and the module under test performs no work until
  `open()` is called.
*/
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  ArtistOpenError,
  artistOpenKey,
  createArtistOpener,
  type ArtistOpenPhase,
} from './artistSync.ts';

type GatewayResult = { slug?: string | null } | null;

function build(options: {
  getArtist?: (slug: string) => Promise<GatewayResult>;
  importArtist?: (
    songkickId: string,
    provider: string,
    data: Record<string, unknown>,
  ) => Promise<GatewayResult>;
}) {
  const calls = {
    getArtist: [] as string[],
    importArtist: [] as Array<{
      songkickId: string;
      provider: string;
      data: Record<string, unknown>;
    }>,
    navigated: [] as string[],
  };

  const opener = createArtistOpener({
    getArtist: async (slug) => {
      calls.getArtist.push(slug);
      return options.getArtist
        ? options.getArtist(slug)
        : Promise.resolve(null);
    },
    importArtist: async (songkickId, provider, data) => {
      calls.importArtist.push({ songkickId, provider, data });
      return options.importArtist
        ? options.importArtist(songkickId, provider, data)
        : Promise.resolve(null);
    },
    navigate: (slug) => {
      calls.navigated.push(slug);
    },
  });

  return { opener, calls };
}

test('an artist that already exists is opened without importing', async () => {
  const { opener, calls } = build({
    getArtist: async () => ({ slug: 'demi-lovato' }),
  });

  const opened = await opener.open({
    slug: 'demi-lovato',
    songkickId: '976211',
    name: 'Demi Lovato',
  });

  assert.equal(opened, 'demi-lovato');
  assert.deepEqual(calls.navigated, ['demi-lovato']);
  assert.deepEqual(calls.getArtist, ['demi-lovato']);
  assert.deepEqual(calls.importArtist, []);
});

test('an unimported artist is imported by Songkick id, never by name', async () => {
  const { opener, calls } = build({
    getArtist: async () => {
      throw new Error('404');
    },
    importArtist: async () => ({ slug: 'post-malone' }),
  });

  const opened = await opener.open({
    // The Songkick-namespace slug of the lineup entry. It is data, and is
    // deliberately never looked up: only a GigCrowd slug may be.
    slug: null,
    songkickId: '8508053',
    name: 'Post Malone',
  });

  assert.equal(opened, 'post-malone');

  // One lookup at most, keyed by the stored slug - and one import, keyed
  // by the Songkick id with the provider spelled out. The name travelled
  // only as data; nothing was matched by it.
  assert.deepEqual(calls.importArtist, [
    {
      songkickId: '8508053',
      provider: 'songkick',
      data: {
        name: 'Post Malone',
        image: null,
        url: null,
      },
    },
  ]);
});

test('the Songkick id is the identity the import runs on', async () => {
  const { opener, calls } = build({
    importArtist: async () => ({ slug: 'racionais-mcs' }),
  });

  await opener.open({ songkickId: '147146', name: "Racionais MC's" });

  assert.equal(calls.importArtist[0].songkickId, '147146');
  assert.equal(calls.importArtist[0].provider, 'songkick');
});

test('repeated clicks share one in-flight operation', async () => {
  let release: (value: GatewayResult) => void = () => undefined;

  const pending = new Promise<GatewayResult>((resolve) => {
    release = resolve;
  });

  const { opener, calls } = build({
    importArtist: () => pending,
  });

  const identity = { songkickId: '8508053', name: 'Post Malone' };

  const first = opener.open(identity);
  const second = opener.open(identity);

  // Both presses resolved to the same running promise, not two imports.
  assert.equal(first, second);

  release({ slug: 'post-malone' });

  assert.equal(await first, 'post-malone');
  assert.equal(await second, 'post-malone');
  assert.equal(calls.importArtist.length, 1);
});

test('once an operation succeeds, a later click reuses the known artist', async () => {
  const { opener, calls } = build({
    getArtist: async () => {
      throw new Error('should not be reached');
    },
    importArtist: async () => ({ slug: 'post-malone' }),
  });

  await opener.open({ songkickId: '8508053', name: 'Post Malone' });
  await opener.open({ songkickId: '8508053', name: 'Post Malone' });

  // The first press imported; the second knew the artist already - by the
  // id the lineup stated - and went straight to their page. One import,
  // one lookup at most, no second provider round trip.
  assert.equal(calls.importArtist.length, 1);
  assert.deepEqual(calls.getArtist, []);
  assert.deepEqual(calls.navigated, ['post-malone', 'post-malone']);
});

test('an entry with neither a slug nor an id fails as unidentifiable', async () => {
  const { opener, calls } = build({});

  const failure = await opener
    .open({ name: 'Some Name From A Poster' })
    .then(() => null)
    .catch((error: unknown) => error);

  assert.ok(failure instanceof ArtistOpenError);
  assert.equal(failure.reason, 'unidentifiable');

  // Nothing was looked up and nothing was imported: with no id there is
  // no safe key, and matching by name is the guess this flow exists to
  // avoid.
  assert.deepEqual(calls.getArtist, []);
  assert.deepEqual(calls.importArtist, []);
  assert.deepEqual(calls.navigated, []);
});

test('a provider failure surfaces as a provider error', async () => {
  const { opener } = build({
    importArtist: async () => {
      throw new Error('Songkick timed out');
    },
  });

  const failure = await opener
    .open({ songkickId: '8508053', name: 'Post Malone' })
    .then(() => null)
    .catch((error: unknown) => error);

  assert.ok(failure instanceof ArtistOpenError);
  assert.equal(failure.reason, 'provider');
});

test('an import that returns no slug fails as a provider error', async () => {
  const { opener } = build({
    importArtist: async () => null,
  });

  const failure = await opener
    .open({ songkickId: '8508053', name: 'Post Malone' })
    .then(() => null)
    .catch((error: unknown) => error);

  assert.ok(failure instanceof ArtistOpenError);
  assert.equal(failure.reason, 'provider');
});

test('the phases are reported in the order they run', async () => {
  const phases: ArtistOpenPhase[] = [];

  const { opener } = build({
    getArtist: async () => {
      throw new Error('404');
    },
    importArtist: async () => ({ slug: 'post-malone' }),
  });

  await opener.open(
    { slug: 'demi-lovato', songkickId: '8508053', name: 'Post Malone' },
    (phase) => phases.push(phase),
  );

  assert.deepEqual(phases, ['lookup', 'import']);
});

test('the dedup key prefers the Songkick id, and is null without one', () => {
  assert.equal(
    artistOpenKey({ songkickId: '976211', slug: 'demi-lovato' }),
    'songkick:976211',
  );

  assert.equal(
    artistOpenKey({ slug: 'demi-lovato' }),
    'slug:demi-lovato',
  );

  assert.equal(artistOpenKey({ name: 'Demi Lovato' }), null);
});
