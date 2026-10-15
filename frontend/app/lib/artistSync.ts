/*
  Opening one artist from a lineup: find them here, or bring them here.

  A lineup announces many more artists than GigCrowd has imported. Clicking a
  name is the request to have that artist *here* - and it is the only thing
  that may import: rendering a page, prefetching a route or resolving a bill
  never does. The identity used is always the Songkick artist id the lineup
  announced; a name is carried as a hint and never as a match.

  This module is deliberately pure logic over injected calls, so the rules
  that matter are testable without a browser:

  * an artist that already exists is opened by their slug, and nothing is
    imported for them;
  * an artist that does not exist yet is imported by Songkick id, once, and
    then opened under the slug the import returned;
  * repeated clicks while the first is still running share the one operation
    instead of starting concurrent imports for the same artist;
  * an artist opened once this session is opened again directly - by the
    same Songkick id - without a second lookup or import;
  * a lineup entry carrying neither a slug nor an id fails as
    `unidentifiable` - there is no safe key to look anyone up by, and
    guessing by name would risk opening the wrong artist;
  * provider failures surface as `provider`, distinguishable from "could not
    be identified", so the caller can offer a retry that means something.

  Nothing here runs on import of the module: a page renders, and the flow
  starts only when `open()` is called.
*/

export type ArtistOpenPhase = 'lookup' | 'import';

export type ArtistOpenFailure = 'unidentifiable' | 'provider';

export class ArtistOpenError extends Error {
  readonly reason: ArtistOpenFailure;

  constructor(reason: ArtistOpenFailure, message?: string) {
    super(message ?? reason);
    this.name = 'ArtistOpenError';
    this.reason = reason;
  }
}

/** One lineup performer, as the page received them. */
export interface LineupArtistIdentity {
  /** The GigCrowd slug, when the entry resolved to an imported artist. */
  slug?: string | null;
  /** The Songkick artist id the lineup announced. */
  songkickId?: string | null;
  /** Displayed, and passed along as a hint - never used to match. */
  name?: string | null;
  image?: string | null;
  url?: string | null;
}

export interface ArtistGateway {
  /** The stored artist, or a rejection/`null` when there is none here. */
  getArtist(
    slug: string,
  ): Promise<{ slug?: string | null } | null>;

  /** Import by Songkick id, returning the canonical record. */
  importArtist(
    songkickId: string,
    provider: string,
    data: Record<string, unknown>,
  ): Promise<{ slug?: string | null } | null>;
}

export interface ArtistOpener {
  /**
   * Open this artist, resolving with the slug that was navigated to.
   * Deduplicated per artist while a call is in flight.
   */
  open(
    identity: LineupArtistIdentity,
    onPhase?: (phase: ArtistOpenPhase) => void,
  ): Promise<string>;
}

/**
 * The one key an artist can be deduplicated by: their Songkick id when the
 * lineup stated one, otherwise the GigCrowd slug the entry resolved to.
 * Returns `null` when neither exists - nothing safe to look up by.
 */
export function artistOpenKey(
  identity: LineupArtistIdentity,
): string | null {
  const songkickId = identity.songkickId?.trim();

  if (songkickId) {
    return `songkick:${songkickId}`;
  }

  const slug = identity.slug?.trim();

  if (slug) {
    return `slug:${slug}`;
  }

  return null;
}

export function createArtistOpener({
  getArtist,
  importArtist,
  navigate,
}: ArtistGateway & {
  navigate: (slug: string) => void;
}): ArtistOpener {
  const inFlight = new Map<string, Promise<string>>();

  /*
    Where an artist was opened, remembered for this session. A successful
    press navigated away, so this mostly guards the return trip: coming back
    to the same bill and pressing the same name again looks the artist up by
    the slug already known instead of importing a second time.
  */
  const resolved = new Map<string, string>();

  async function run(
    identity: LineupArtistIdentity,
    onPhase?: (phase: ArtistOpenPhase) => void,
  ): Promise<string> {
    const songkickId = identity.songkickId?.trim() ?? '';
    const slug = identity.slug?.trim() ?? '';

    if (slug) {
      onPhase?.('lookup');

      try {
        const existing = await getArtist(slug);

        if (existing?.slug) {
          navigate(existing.slug);
          return existing.slug;
        }
      } catch {
        // Not here under this slug - and a network failure reads the same
        // from here. Either way the import below is the authority on who
        // this is: it validates the identity against the artist's own
        // Songkick page, which a lookup never does.
      }
    }

    if (!songkickId) {
      // No id and no stored page: the lineup gave nothing a lookup can be
      // keyed by. Matching by name is exactly the guess this flow exists
      // to avoid, so this fails instead of opening somebody else.
      throw new ArtistOpenError(
        'unidentifiable',
        'This lineup entry carries no Songkick id and no stored artist.',
      );
    }

    onPhase?.('import');

    let imported: { slug?: string | null } | null;

    try {
      imported = await importArtist(songkickId, 'songkick', {
        name: identity.name ?? null,
        image: identity.image ?? null,
        url: identity.url ?? null,
      });
    } catch (error) {
      throw new ArtistOpenError(
        'provider',
        error instanceof Error ? error.message : String(error),
      );
    }

    if (!imported?.slug) {
      throw new ArtistOpenError(
        'provider',
        'The import returned no slug.',
      );
    }

    navigate(imported.slug);
    return imported.slug;
  }

  return {
    open(identity, onPhase) {
      const key = artistOpenKey(identity);

      if (!key) {
        return Promise.reject(
          new ArtistOpenError(
            'unidentifiable',
            'This lineup entry carries no Songkick id and no stored artist.',
          ),
        );
      }

      const known = resolved.get(key);

      if (known) {
        navigate(known);
        return Promise.resolve(known);
      }

      const pending = inFlight.get(key);

      if (pending) {
        return pending;
      }

      const promise = run(identity, onPhase)
        .then((slug) => {
          resolved.set(key, slug);
          return slug;
        })
        .finally(() => {
          inFlight.delete(key);
        });

      inFlight.set(key, promise);

      return promise;
    },
  };
}
