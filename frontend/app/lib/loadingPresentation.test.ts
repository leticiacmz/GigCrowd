/*
  What every loading state in the app must look like and say.

  The repository has no React test harness, so - like lineupPresentation -
  these tests read the files that ship and pin the properties that matter
  as files: one shared icon-and-gradient-ring component with sizes, an
  announced message, no fabricated progress, honest messages at the call
  sites that used to lie, and a reduced-motion rule that stops the ring.
  Visual layout and live behaviour in a browser remain manual checks, and
  saying so is more honest than pretending a file read renders a component.
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

test('the shared loading state carries the brand icon and a gradient ring', () => {
  const component = read('components/LoadingState.tsx');

  const icon = component.match(/src="([^"]*icon-192x192\.png)"/);
  assert.ok(icon, 'the loading state must show the shipped GigCrowd icon');
  assert.ok(
    existsSync(path.join(frontendRoot, 'public', 'icons', 'icon-192x192.png')),
    'the referenced brand icon must exist in public/icons',
  );

  assert.ok(
    component.includes('loading-orbit'),
    'the ring must come from the shared orbit class',
  );

  const css = read('app/globals.css');
  const ringRule = css.match(
    /\.artist-sync-orbit::before,\s*\.loading-orbit::before\s*\{[^}]*\}/,
  );

  assert.ok(ringRule, 'both loading rings must be drawn by one shared rule');
  assert.ok(
    ringRule[0].includes('--gradient-from') &&
      ringRule[0].includes('--gradient-to'),
    'the ring must use the gradient design tokens, not a solid colour',
  );
  assert.ok(
    css.includes('.loading-orbit--section') &&
      css.includes('.loading-orbit--inline'),
    'the orbit must offer section and inline sizes beside the page size',
  );
});

test('the loading state announces itself and is sized by context', () => {
  const component = read('components/LoadingState.tsx');

  assert.ok(component.includes('role="status"'));
  assert.ok(component.includes('aria-live="polite"'));
  assert.ok(
    component.includes("size?: 'page' | 'section' | 'inline'"),
    'the component must offer the three sizes the app needs',
  );
  assert.ok(
    component.includes("icon: 'h-10 w-10 rounded-lg'") &&
      component.includes("icon: 'h-6 w-6 rounded-md'") &&
      component.includes("icon: 'h-4 w-4 rounded'"),
    'each size must scale the centred icon with its ring',
  );
});

test('no loading state invents progress or schedules its own end', () => {
  // Every loading here belongs to real async work; when the work ends the
  // loading ends, because nothing in these components runs on a timer.
  for (const file of [
    'components/LoadingState.tsx',
    'components/ui/ArtistSyncLoading.tsx',
  ]) {
    const source = read(file);

    assert.ok(!source.includes('setTimeout('), `${file} must not use timers`);
    assert.ok(
      !source.includes('Math.random('),
      `${file} must not fabricate progress`,
    );
  }
});

test('the ring stops under prefers-reduced-motion, together with the artist orbit', () => {
  const css = read('app/globals.css');

  assert.ok(css.includes('@keyframes artist-sync-spin'));
  assert.ok(
    /\.artist-sync-orbit::before,\s*\.loading-orbit::before\s*\{[^}]*animation:\s*artist-sync-spin/.test(
      css,
    ),
    'both rings must share one keyframes',
  );

  const reducedBlock = css.match(
    /prefers-reduced-motion: reduce[^{]*\{[^}]*artist-sync-orbit[^}]*\}/,
  );

  assert.ok(reducedBlock, 'the orbit needs its own reduced-motion rule');
  assert.ok(reducedBlock[0].includes('animation: none'));
  assert.ok(
    reducedBlock[0].includes('loading-orbit'),
    'the generic ring must stop under reduced motion too',
  );
});

test('the artist-events page loads with a translated message, not a literal', () => {
  const page = read('app/[locale]/artists/[slug]/events/page.tsx');

  assert.ok(
    !page.includes('message="Loading events..."'),
    'the English literal must be gone',
  );
  assert.ok(
    page.includes("message={t('loading')}"),
    'the page must load through its own namespace',
  );
});

test('the notifications page loads with a loading message, not its title', () => {
  const page = read('app/[locale]/notifications/page.tsx');

  assert.ok(
    !page.includes("message={t('title')}"),
    'the page title is not a loading message',
  );
  assert.ok(
    page.includes("message={tCommon('loading')}"),
    'the loader must announce that it is loading',
  );
});

test('the follow button says it is loading, not that artists are loading', () => {
  const page = read('app/[locale]/artists/[slug]/page.tsx');

  assert.ok(
    !/followLoading\s*\n?\s*\?\s*t\('loadingRelated'\)/.test(page),
    '"Loading related artists..." is a section message, not a follow action',
  );
  assert.ok(
    /followLoading\s*\n?\s*\?\s*tCommon\('loading'\)/.test(page),
    'the button must use the generic loading message while it works',
  );
});

test('the auth guard and the own-profile redirect show the loading state, not a blank screen', () => {
  const guard = read('components/auth/RequireAuth.tsx');

  assert.ok(
    guard.includes('<LoadingState'),
    'the guard must show a loading state while the session is unknown',
  );
  assert.ok(
    !/if \(authorized !== true\) \{\s*return null;/.test(guard),
    'a blank frame is not a loading state',
  );

  const profile = read('app/[locale]/profile/page.tsx');
  assert.ok(
    !profile.includes('message=""'),
    'the redirect wait must announce itself',
  );
});

test('the text-only section loaders were consolidated into the shared component', () => {
  const postCard = read('components/community/PostCard.tsx');
  assert.ok(postCard.includes('<LoadingState'));
  assert.ok(
    postCard.includes('size="inline"'),
    'comments load inline, sized to a row',
  );

  const profilePanel = read('components/profile/ProfilePanel.tsx');
  assert.ok(profilePanel.includes('size="inline"'));

  const artistPage = read('app/[locale]/artists/[slug]/page.tsx');
  assert.ok(
    /relatedLoading \? \(\s*<Card[^>]*>\s*<LoadingState/.test(artistPage),
    'the related-artists wait must render the shared state inside its card',
  );
});

test('every locale carries the loading messages the fixes rely on', () => {
  for (const locale of ['en', 'pt-BR', 'es']) {
    const messages = JSON.parse(read(`messages/${locale}.json`));

    assert.ok(
      messages.common?.loading,
      `${locale} is missing common.loading`,
    );
    assert.ok(
      messages.artistEvents?.loading,
      `${locale} is missing artistEvents.loading`,
    );
    assert.ok(
      messages.artistSync?.searching,
      `${locale} is missing artistSync.searching`,
    );
  }
});
