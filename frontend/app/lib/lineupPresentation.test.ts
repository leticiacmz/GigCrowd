/*
  The presentation contracts this project holds without a DOM renderer.

  The repository has no React test harness, and installing one to assert
  markup would be heavier than the rules being held. These tests therefore
  read the files that ship and pin the properties that matter as files:
  the lineup renders no photographs and imports nothing that could fetch,
  the loading state uses the brand asset that already exists and respects
  reduced motion, and every locale carries the artist-sync messages. What
  they cannot cover is visual layout and event wiring inside a browser -
  those remain manual checks, and saying so is more honest than pretending
  a file read renders a component.
*/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(here, '..', '..');

function read(relative: string): string {
  return readFileSync(path.join(frontendRoot, relative), 'utf8');
}

test('the lineup renders no artist photographs', () => {
  const card = read('components/festival/LineupPerformerCard.tsx');

  assert.ok(
    !card.includes('performer.image'),
    'the performer card must not read an image off the lineup entry',
  );

  assert.ok(
    !card.includes('<img'),
    'the performer card must render no <img> at all',
  );
});

test('rendering a lineup entry imports nothing that could fetch', () => {
  const card = read('components/festival/LineupPerformerCard.tsx');

  // The card's only dependencies are navigation and translations. No api
  // client, no artist module, no image loader: rendering the bill cannot
  // import an artist or call a provider, whatever the entry carries.
  assert.ok(!card.includes("from '@/app/lib/api'"));
  assert.ok(!card.includes('artistSync'));
  assert.ok(!card.includes('fetch('));
});

test('an identified entry with no page here links to its import address', () => {
  const card = read('components/festival/LineupPerformerCard.tsx');

  // The announced id is the identity the import validates; the card builds
  // the address locally (it must not import the artist module), in the same
  // shape the rest of the app builds.
  assert.ok(card.includes('songkick_id'));
  assert.ok(card.includes('artists/import/songkick/'));
  assert.ok(card.includes('?name='));

  // An entry the import will act on is still marked unlinked - nothing here
  // claims the artist exists yet - and an entry with no id stays a name.
  assert.ok(card.includes('data-lineup-linked="false"'));
  assert.ok(card.includes('data-lineup-action="import"'));
});

test('the artist loading state uses the existing brand icon', () => {
  const component = read('components/ui/ArtistSyncLoading.tsx');

  const icon = component.match(/src="([^"]*icon-192x192\.png)"/);

  assert.ok(icon, 'the loading state must show the shipped GigCrowd icon');

  // The asset it names is the one already in public/ - no new logo.
  assert.ok(
    existsSync(path.join(frontendRoot, 'public', 'icons', 'icon-192x192.png')),
    'the referenced brand icon must exist in public/icons',
  );
});

test('the artist loading state announces itself without repeating', () => {
  const component = read('components/ui/ArtistSyncLoading.tsx');

  assert.ok(component.includes('role="status"'));
  assert.ok(component.includes('aria-live="polite"'));
});

test('the artist page says it is waiting on the events, not on finding the artist', () => {
  // The first open of an artist is the gigography sync: the artist is
  // already identified, so a "finding artist" message for the whole
  // multi-minute wait misstates what is happening. The page must ask for
  // the events phase, and the component must know that phase.
  const page = read('app/[locale]/artists/[slug]/page.tsx');

  assert.ok(
    page.includes('phase="events"'),
    'the artist page loading state must announce the events wait',
  );

  const component = read('components/ui/ArtistSyncLoading.tsx');

  assert.ok(component.includes("'events'"));
  assert.ok(component.includes("t('events')"));
});

test('the loading ring stops under prefers-reduced-motion', () => {
  const css = read('app/globals.css');

  assert.ok(css.includes('@keyframes artist-sync-spin'));

  // The ring has its own reduced-motion rule that switches it off
  // outright, rather than relying on the project-wide shortened
  // animation duration, which would leave it looping.
  const reducedBlock = css.match(
    /prefers-reduced-motion: reduce[^{]*\{[^}]*artist-sync-orbit[^}]*\}/,
  );

  assert.ok(reducedBlock, 'the orbit needs its own reduced-motion rule');
  assert.ok(reducedBlock[0].includes('animation: none'));
});

test('every locale carries the artist-sync messages, and the retired artists tab does not', () => {
  for (const locale of ['en', 'pt-BR', 'es']) {
    const messages = JSON.parse(read(`messages/${locale}.json`));

    for (const key of [
      'searching',
      'events',
      'importing',
      'failed',
      'unidentifiable',
      'retry',
      'close',
    ]) {
      assert.ok(
        messages.artistSync?.[key],
        `${locale} is missing artistSync.${key}`,
      );
    }

    assert.ok(
      !('artists' in (messages.nav ?? {})),
      `${locale} still ships the retired nav.artists tab`,
    );
  }
});
