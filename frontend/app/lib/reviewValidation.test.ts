/*
  What a review is, from the form that writes one to the card that shows one.

  An opinion is a rating or some words - each optional on its own - and a
  photo alone is never one, whitespace says nothing, and a rating that was
  never given stays absent rather than becoming a zero. The rule lives in
  one module so the editor, the dialog, the event page and these tests
  cannot drift apart; these tests exercise the rule directly and pin the
  files that ship to using it. Live rendering in a browser remains a
  manual check, and saying so is more honest than pretending a file read
  draws stars.
*/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { logCarriesReview, reviewCanBeSaved } from './reviewValidation.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(here, '..', '..');

function read(relative: string): string {
  return readFileSync(path.join(frontendRoot, relative), 'utf8');
}

const PHOTO = 'https://example.test/p.jpg';

test('a rating on its own is a complete review', () => {
  assert.equal(reviewCanBeSaved(4, null), true);
  assert.equal(reviewCanBeSaved(1, ''), true);
  assert.equal(reviewCanBeSaved(5, '   '), true);
});

test('words without stars are a complete review', () => {
  assert.equal(reviewCanBeSaved(null, 'Loud, tight, worth the trip'), true);
  assert.equal(reviewCanBeSaved(0, 'Worth every minute'), true);
});

test('stars and words together are a review', () => {
  assert.equal(reviewCanBeSaved(5, 'Encore!'), true);
});

test('an empty form is not a review', () => {
  assert.equal(reviewCanBeSaved(null, null), false);
  assert.equal(reviewCanBeSaved(null, ''), false);
  assert.equal(reviewCanBeSaved(0, ''), false);
});

test('whitespace says nothing and cannot be saved', () => {
  assert.equal(reviewCanBeSaved(null, '   '), false);
  assert.equal(reviewCanBeSaved(null, '\t\n'), false);
});

test('the writing rule never sees a photo', () => {
  // The photo is detail about an opinion, not one: it is deliberately not
  // a parameter, so a photo can neither complete the rule nor be what the
  // form submits on. Photo-only and empty submissions are therefore the
  // same refusal - nothing to save - and the backend refuses them again.
  assert.equal(reviewCanBeSaved.length, 2);
  assert.equal(reviewCanBeSaved(null, ''), false);
  assert.ok(PHOTO);
});

test('reading keeps every row that already is a review', () => {
  assert.equal(logCarriesReview({ rating: 4 }), true, 'a bare rating');
  assert.equal(logCarriesReview({ review: 'Great night' }), true, 'words');
  assert.equal(logCarriesReview({ photo_url: PHOTO }), true, 'a legacy photo');
  assert.equal(
    logCarriesReview({ rating: 4, review: 'Great', photo_url: PHOTO }),
    true,
    'all three',
  );
});

test('reading refuses rows that hold no opinion', () => {
  assert.equal(logCarriesReview({ status: 'went' }), false);
  assert.equal(logCarriesReview({ review: '   ' }), false);
  assert.equal(logCarriesReview({ rating: 0 }), false);
  assert.equal(logCarriesReview({ rating: null }), false);
  assert.equal(logCarriesReview({ photo_url: '' }), false);
});

test('the editor decides through the shared rule, and states an absent rating as absent', () => {
  const editor = read('components/ReviewEditor.tsx');

  assert.ok(
    editor.includes('reviewCanBeSaved(rating, review)'),
    'the save gate must come from the shared rule',
  );
  assert.ok(
    !/canSubmit = [^\n]*photoUrl/.test(editor),
    'a photo must never enable the save on its own',
  );
  assert.ok(
    !editor.includes('rating >= 1 && hasSomethingToSay'),
    'the old rating-plus-text-plus-photo rule must be gone',
  );
  assert.ok(
    editor.includes('rating: rating >= 1 ? rating : null'),
    'a review without stars must be sent with no rating at all, not a 0',
  );
  assert.ok(
    editor.includes('!hasOpinion &&'),
    'the hint must say what is missing, not what is present',
  );
});

test('the dialog reads what the log carries, not only its text', () => {
  const dialog = read('components/ReviewDialog.tsx');

  assert.equal(
    (dialog.match(/logCarriesReview\(showLog\)/g) ?? []).length,
    2,
    'both the title and the delete offer must read the same predicate',
  );
  assert.ok(
    !dialog.includes('showLog?.review ? t(\'editTitle\')'),
    'a rating-only or legacy-photo review must open as an edit',
  );
});

test('the event page treats a rating-less opinion as the person\'s review', () => {
  const page = read('app/[locale]/events/[id]/page.tsx');

  assert.ok(
    page.includes('logCarriesReview(showLog)'),
    'the own-review gate must read rating, words or legacy photo',
  );
  assert.ok(
    page.includes('rating: showLog.rating ?? null'),
    'an absent rating must reach the card as absence',
  );
  assert.ok(
    !page.includes('showLog?.rating && isEventPast'),
    'the rating-only gate must be gone',
  );
});

test('the card draws stars only when a rating exists', () => {
  const card = read('components/ReviewCard.tsx');

  assert.ok(
    card.includes('typeof review.rating === \'number\''),
    'stars must be conditional on an actual rating',
  );
  assert.ok(
    !/<ReviewStars rating=\{review\.rating\} \/>\s*\n\s*<time/.test(card),
    'the unconditional star row must be gone',
  );
});

test('the types allow a review without a rating', () => {
  const payload = read('app/types/review.ts');
  assert.ok(
    payload.includes('rating: number | null'),
    'the payload must be able to state that there is no rating',
  );

  const profile = read('app/types/profile.ts');
  assert.ok(
    !profile.includes('  rating: number;'),
    'a listed review must not be typed as always rated',
  );
  assert.ok(
    profile.includes('rating?: number | null'),
    'the listed rating must be optional',
  );
});

test('every locale tells the new rule in the hint', () => {
  for (const locale of ['en', 'pt-BR', 'es']) {
    const messages = JSON.parse(read(`messages/${locale}.json`));
    const hint: string = messages.review?.needsSomething ?? '';

    assert.ok(hint, `${locale} is missing review.needsSomething`);

    if (locale === 'en') {
      assert.ok(
        !hint.includes('a rating on its own is not a review'),
        'the old rule must not be told any more',
      );
      assert.ok(hint.includes('a photo on its own is not a review'));
    }

    if (locale === 'pt-BR') {
      assert.ok(!hint.includes('uma nota sozinha não é uma avaliação'));
      assert.ok(hint.includes('uma foto sozinha não é uma avaliação'));
    }

    if (locale === 'es') {
      assert.ok(!hint.includes('una puntuación por sí sola no es una reseña'));
      assert.ok(hint.includes('una foto por sí sola no es una reseña'));
    }
  }
});

test('the browser script pins the save gate the form now enforces', () => {
  const script = read('verify_browser.py');

  assert.ok(
    script.includes('a rating on its own can be saved'),
    'the e2e must expect the rating-alone save to be enabled',
  );
  assert.ok(
    !script.includes('a rating on its own is still not a review'),
    'the inverted assertion must be gone',
  );
  assert.ok(
    script.includes('an empty review cannot be saved'),
    'the empty-form refusal must stay pinned',
  );
});
