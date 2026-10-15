/*
  One rule about every request a page can outlive: only the most recently
  started one may write its answer.

  React keeps a page component mounted while its parameters change, so the
  async loaders of a previous page (its event id, its show log) can still be
  in flight when the next page starts loading. A response that arrives late
  would otherwise overwrite the current page's state with the previous
  page's data - attendance and content from a different event rendered as if
  they belonged to this one. The guard gives each call a token and lets a
  caller discard every answer that is no longer the newest.
*/

export interface RequestGuard {
  /** Claim the next request; every older claim is now stale. */
  next(): number;
  /** Whether this token still identifies the newest request. */
  isCurrent(token: number): boolean;
}

export function createRequestGuard(): RequestGuard {
  let latest = 0;

  return {
    next() {
      latest += 1;
      return latest;
    },
    isCurrent(token: number) {
      return token === latest;
    },
  };
}
