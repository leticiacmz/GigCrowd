/*
  What a row of the unified timeline must look like.

  Like the other file-reading tests here (there is no React harness), these
  pin the properties of the feed row as it ships: the rating is drawn by the
  shared read-only stars above the words it rates, the row's only navigation
  target is named by where it goes rather than by a redundant instruction,
  and the data-testid hooks the browser suite depends on all survive.
*/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(here, '..', '..');

const page = readFileSync(
  path.join(frontendRoot, 'app/[locale]/feed/page.tsx'),
  'utf8',
);

test('a rating in the feed is the shared stars component, not rows of glyphs', () => {
  assert.ok(
    page.includes("import ReviewStars from '@/components/ReviewStars'"),
    'the feed must draw ratings with the one stars component',
  );
  assert.ok(
    !/{'★'\.repeat\(item\.rating\)\}/.test(page),
    'the hand-drawn star row must be gone',
  );
  assert.ok(
    /item\.rating \? \(\s*<div[^>]*>\s*<ReviewStars rating=\{item\.rating\} \/>\s*<\/div>\s*\)/.test(
      page,
    ),
    'the stars belong above the review text, only when a rating exists',
  );
});

test('a target link is named by its destination, not by a redundant verb', () => {
  assert.ok(
    !/\$\{item\.target\.title\} · \$\{t\('viewEvent'\)\}/.test(page),
    'the show title must not carry a "· View event" suffix',
  );
  assert.ok(
    !/\$\{artistName\} · \$\{t\('viewPost'\)\}/.test(page),
    'the artist name must not carry a "· View post" suffix',
  );
  assert.ok(
    /label: item\.target\?\.title \|\| t\('viewEvent'\)/.test(page),
    'the title alone names the link, with the generic verb only as fallback',
  );
});

test('the row keeps every hook the browser suite selects by', () => {
  for (const testid of [
    'feed-item',
    'feed-actor-link',
    'feed-verb',
    'feed-target-link',
    'feed-timestamp',
    'feed-image',
  ]) {
    assert.ok(
      page.includes(`data-testid="${testid}"`),
      `the ${testid} hook must survive the restructure`,
    );
  }
});

test('the timestamp renders as a real <time> with the machine-readable value', () => {
  assert.ok(
    /<time\s+dateTime=\{item\.created_at\}\s+data-testid="feed-timestamp"/.test(
      page.replace(/\n\s+/g, ' '),
    ),
    'the timestamp stays a time element for assistive technology',
  );
});
