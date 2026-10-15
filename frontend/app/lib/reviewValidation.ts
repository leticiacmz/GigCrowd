/**
 * The rule that decides whether a review may be saved, and the rule that
 * decides whether a stored one is a review - kept here so the editor that
 * writes, the dialog that reads and the tests that pin the rule can never
 * drift apart.
 *
 * Writing and reading are deliberately different. Writing demands an
 * opinion - a rating or some words - because a photo on its own is
 * evidence rather than an opinion and whitespace says nothing at all.
 * Reading is broader: rows stored under the older rule carry a photo, or
 * a rating without text, and they are reviews already - a reader is not
 * written out of the profile by being stricter than the rule that
 * recorded them.
 */

/**
 * Whether a form holds an opinion worth saving: at least a rating or some
 * non-empty words. The photo never counts here; it is detail about an
 * opinion, not one.
 */
export function reviewCanBeSaved(
  rating: number | null | undefined,
  review: string | null | undefined,
): boolean {
  return (
    (rating != null && rating >= 1) ||
    Boolean(review && review.trim().length > 0)
  );
}

/**
 * Whether a stored show log carries a review: a rating, some words, or the
 * photo only a legacy row was written with. A rating of 0 reads as the
 * absence it is, never as a verdict.
 *
 * The shape includes `status` because callers pass whole logs through;
 * only the three fields below are read.
 */
export function logCarriesReview(log: {
  status?: string | null;
  rating?: number | null;
  review?: string | null;
  photo_url?: string | null;
}): boolean {
  return (
    (log.rating != null && log.rating >= 1) ||
    Boolean(log.review && log.review.trim().length > 0) ||
    Boolean(log.photo_url && log.photo_url.trim().length > 0)
  );
}
