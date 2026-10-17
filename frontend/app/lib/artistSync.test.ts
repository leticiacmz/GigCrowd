/*
  Bringing an artist here without making the press wait, as pure logic over
  injected calls.

  Every case maps to a rule the product relies on: a press navigates
  immediately to the artist's import address, repeated opens of the same
  artist share the one import running for them, an artist imported once is
  opened straight from the remembered slug, and a failed import stays
  retryable. The gateway is injected, so nothing here touches the network.

  The last tests pin the pages that ship to those rules as files: the import
  address renders the app's own loading state and waits for nothing else, the
  pages that press names navigate instead of importing, and the artist page
  reads its events again after a first-open synchronization.
*/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import {
  artistImportKey,
  artistImportPath,
  artistPagePath,
  createArtistImportPool,
  type ArtistImportRequest,
  type ImportMemory,
} from './artistSync.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(here, '..', '..');

function read(relative: string): string {
  return readFileSync(path.join(frontendRoot, relative), 'utf8');
}

function fakeMemory(): ImportMemory & { entries: Map<string, string> } {
  const entries = new Map<string, string>();

  return {
    entries,
    read: (key) => entries.get(key) ?? null,
    write: (key, slug) => {
      entries.set(key, slug);
    },
  };
}

const charli: ArtistImportRequest = {
  provider: 'songkick',
  providerArtistId: 'Artist2274326',
  name: 'Charli XCX',
};

test('the import address carries the announced identity and nothing else', () => {
  assert.equal(
    artistImportPath('pt-BR', charli),
    '/pt-BR/artists/import/songkick/Artist2274326?name=Charli%20XCX',
  );

  // A name is a hint; without one the address still imports the id.
  assert.equal(
    artistImportPath('pt-BR', {
      provider: 'songkick',
      providerArtistId: 'Artist2274326',
    }),
    '/pt-BR/artists/import/songkick/Artist2274326',
  );

  // A whitespace-only name is no name.
  assert.equal(
    artistImportPath('en', {
      provider: 'songkick',
      providerArtistId: 'Artist1',
      name: '   ',
    }),
    '/en/artists/import/songkick/Artist1',
  );

  // Characters that would change the address are encoded, not passed on.
  assert.equal(
    artistImportPath('en', {
      provider: 'songkick',
      providerArtistId: 'Artist2',
      name: 'A & B',
    }),
    '/en/artists/import/songkick/Artist2?name=A%20%26%20B',
  );

  // The canonical page address is its own builder.
  assert.equal(
    artistPagePath('pt-BR', 'charli-xcx'),
    '/pt-BR/artists/charli-xcx',
  );
});

test('the identity that names an import is the provider id', () => {
  assert.equal(
    artistImportKey('songkick', 'Artist2274326'),
    'songkick:Artist2274326',
  );

  // The same id under another provider is another artist.
  assert.notEqual(
    artistImportKey('songkick', '1'),
    artistImportKey('spotify', '1'),
  );
});

test('repeated opens of the same artist share the one import', async () => {
  const pool = createArtistImportPool({ memory: fakeMemory() });

  let calls = 0;
  let release: (outcome: { slug: string }) => void = () => {};
  const importer = () => {
    calls += 1;
    return new Promise<{ slug: string }>((resolve) => {
      release = resolve;
    });
  };

  const first = pool.open(charli, importer);
  const second = pool.open(charli, importer);

  assert.equal(calls, 1, 'a second open while the first runs must not import');
  assert.equal(first, second, 'the second open joins the running import');

  release({ slug: 'charli-xcx' });

  assert.deepEqual(await first, { slug: 'charli-xcx' });
  assert.deepEqual(await second, { slug: 'charli-xcx' });
  assert.equal(calls, 1);
});

test('an artist imported once is opened from the remembered slug', async () => {
  const pool = createArtistImportPool({ memory: fakeMemory() });

  let calls = 0;
  const importer = () => {
    calls += 1;
    return Promise.resolve({ slug: 'charli-xcx' });
  };

  await pool.open(charli, importer);

  assert.equal(pool.known(charli), 'charli-xcx');

  const again = await pool.open(charli, importer);

  assert.deepEqual(again, { slug: 'charli-xcx' });
  assert.equal(calls, 1, 'a remembered artist must not be imported again');
});

test('a fresh pool reads the slug the session remembers', async () => {
  const memory = fakeMemory();

  const first = createArtistImportPool({ memory });
  await first.open(charli, () => Promise.resolve({ slug: 'charli-xcx' }));

  // A page reload keeps the session storage but loses the module state.
  const second = createArtistImportPool({ memory });

  assert.equal(second.known(charli), 'charli-xcx');

  let calls = 0;
  const outcome = await second.open(charli, () => {
    calls += 1;
    return Promise.resolve({ slug: 'somebody-else' });
  });

  assert.deepEqual(outcome, { slug: 'charli-xcx' });
  assert.equal(calls, 0, 'session memory must be asked before the provider');
});

test('a failed import is forgotten, so trying again is a real attempt', async () => {
  const pool = createArtistImportPool({ memory: fakeMemory() });

  await assert.rejects(
    pool.open(charli, () => Promise.reject(new Error('provider down'))),
  );

  assert.equal(pool.known(charli), null);

  const outcome = await pool.open(charli, () =>
    Promise.resolve({ slug: 'charli-xcx' }),
  );

  assert.deepEqual(outcome, { slug: 'charli-xcx' });
});

test('different artists never share an import', async () => {
  const pool = createArtistImportPool({ memory: fakeMemory() });

  const calls: string[] = [];
  const importer = (request: ArtistImportRequest) => {
    calls.push(request.providerArtistId);
    return Promise.resolve({ slug: `slug-${request.providerArtistId}` });
  };

  await Promise.all([
    pool.open(charli, importer),
    pool.open(
      { provider: 'songkick', providerArtistId: 'Artist42', name: 'Other' },
      importer,
    ),
  ]);

  assert.deepEqual(calls, ['Artist2274326', 'Artist42']);
});

test('the import address is a page that shows the app spinner and hands over', () => {
  const page = read('app/[locale]/artists/import/[provider]/[id]/page.tsx');

  assert.ok(page.includes("from '@/app/lib/artistSync'"));
  assert.ok(page.includes('sharedArtistImportPool'));
  assert.ok(page.includes('<ArtistSyncLoading'));
  assert.ok(page.includes('phase="importing"'));
  assert.ok(page.includes('artistPagePath('));
  assert.ok(page.includes('router.replace('));

  // The name travels as a query hint, read after mount so the page stays
  // prerenderable.
  assert.ok(page.includes("get('name')"));

  // A failure is a state of this same page, with a way to try again.
  assert.ok(page.includes('setFailed(true)'));
  assert.ok(page.includes('onRetry'));
});

test('pressing an artist navigates immediately, everywhere', () => {
  const eventsPage = read('app/[locale]/events/page.tsx');

  // The press is a link to the artist's page or their import address; the
  // events page itself never imports and never waits on one.
  assert.ok(eventsPage.includes('artistImportPath('));
  assert.ok(eventsPage.includes('artistPagePath('));
  assert.ok(!eventsPage.includes('artistAPI'));

  for (const file of [
    'components/festival/FestivalDetails.tsx',
    'app/[locale]/events/[id]/page.tsx',
  ]) {
    const source = read(file);

    assert.ok(
      !source.includes('createArtistOpener'),
      `${file} must not build an artist opener on the page`,
    );
    assert.ok(
      !source.includes('artist-open-overlay'),
      `${file} must not hold the reader on an import overlay`,
    );
    assert.ok(
      !source.includes('importArtist'),
      `${file} must not import artists inline`,
    );
  }
});

test('the artist page re-reads its events after a first-open synchronization', () => {
  const page = read('app/[locale]/artists/[slug]/page.tsx');

  assert.ok(page.includes('data?.sync?.attempted'));
  assert.ok(page.includes('await loadArtistEvents()'));

  // The list on screen must be the current artist's: stale answers from a
  // previous artist are discarded, and the page's state is dropped when the
  // slug changes.
  assert.ok(page.includes('createRequestGuard'));
  assert.ok(page.includes('stillMine()'));
});

test('the full listing also re-reads after a first-open synchronization', () => {
  const page = read('app/[locale]/artists/[slug]/events/page.tsx');

  assert.ok(page.includes('data?.sync?.attempted'));
  assert.ok(page.includes('await loadEvents()'));
});
