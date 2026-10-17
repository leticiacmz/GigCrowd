/*
  Bringing an artist here, without parking the reader on the page they
  clicked from.

  A lineup or a search result can name an artist GigCrowd has never imported.
  Opening one of those is the request to have them here, and only that request
  imports - rendering a page never does. The import itself is not fast: the
  backend validates the identity against the artist's own Songkick page and
  then fetches their whole gigography, which can take a minute.

  So a press no longer waits for any of that. It navigates immediately to the
  artist's import address - `/{locale}/artists/import/{provider}/{id}` - which
  shows the app's own loading state and runs the import behind it. The moment
  the import answers with a slug, that page replaces itself with the canonical
  artist page. The identity is always the provider id the source announced; a
  name travels as a hint for the spinner and the identity check, never as a
  match.

  This module is deliberately pure logic over an injected call, so the rules
  that matter are testable without a browser:

  * repeated opens of the same artist - a double press, a React double mount,
    a second visit while the first import is still running - join the one
    running import instead of starting concurrent ones;
  * an artist imported once in this browser session is opened directly from
    the remembered slug, without a second import;
  * a failed import is forgotten the moment it settles, so "try again" is a
    real attempt rather than a replay of the failure;
  * addresses are built one way here, and the pages use that one way.
*/

export interface ArtistImportRequest {
  provider: string;
  providerArtistId: string;
  /** Carried for the spinner and the identity check. Never used to match. */
  name?: string | null;
}

export interface ArtistImportOutcome {
  slug: string;
}

/** The provider id that names one import across presses and mounts. */
export function artistImportKey(
  provider: string,
  providerArtistId: string,
): string {
  return `${provider}:${providerArtistId}`;
}

/**
 * The address that performs this import.
 *
 * It is a page, not an API call, because the reader must be able to be there
 * while the import runs: the address renders the loading state from its first
 * frame and hands over to the artist's real page when the import answers.
 */
export function artistImportPath(
  locale: string,
  request: {
    provider: string;
    providerArtistId: string;
    name?: string | null;
  },
): string {
  const base =
    `/${locale}/artists/import/` +
    `${encodeURIComponent(request.provider)}/` +
    `${encodeURIComponent(request.providerArtistId)}`;

  const name = request.name?.trim();

  return name ? `${base}?name=${encodeURIComponent(name)}` : base;
}

/** The canonical page an imported artist lives at. */
export function artistPagePath(locale: string, slug: string): string {
  return `/${locale}/artists/${slug}`;
}

/**
 * Where one imported slug is remembered, so a repeated open in the same
 * browser session does not pay for a second import.
 */
export interface ImportMemory {
  read(key: string): string | null;
  write(key: string, slug: string): void;
}

const SESSION_PREFIX = 'gigcrowd.artist-import.';

/**
 * Session storage, guarded. A browser that refuses it (private-mode quotas,
 * disabled storage) costs a repeated import, never a broken page: the
 * in-document map beside it still answers for the life of the tab.
 */
export function createSessionImportMemory(): ImportMemory {
  return {
    read(key: string): string | null {
      if (typeof window === 'undefined') {
        return null;
      }

      try {
        return window.sessionStorage.getItem(SESSION_PREFIX + key);
      } catch {
        return null;
      }
    },

    write(key: string, slug: string): void {
      if (typeof window === 'undefined') {
        return;
      }

      try {
        window.sessionStorage.setItem(SESSION_PREFIX + key, slug);
      } catch {
        // See above: memory failing to persist is not the page failing.
      }
    },
  };
}

export type ArtistImporter = (
  request: ArtistImportRequest,
) => Promise<ArtistImportOutcome>;

export interface ArtistImportPool {
  /** The slug this artist was already imported under, if it is known. */
  known(request: ArtistImportRequest): string | null;
  /** Import the artist, or join the import already running for them. */
  open(
    request: ArtistImportRequest,
    importArtist: ArtistImporter,
  ): Promise<ArtistImportOutcome>;
}

export function createArtistImportPool({
  memory = createSessionImportMemory(),
}: {
  memory?: ImportMemory;
} = {}): ArtistImportPool {
  const inFlight = new Map<string, Promise<ArtistImportOutcome>>();
  const completed = new Map<string, string>();

  function known(request: ArtistImportRequest): string | null {
    const key = artistImportKey(
      request.provider,
      request.providerArtistId,
    );

    const remembered = completed.get(key) ?? memory.read(key);

    if (!remembered) {
      return null;
    }

    // Warm the in-document map, so the second question never touches storage.
    completed.set(key, remembered);

    return remembered;
  }

  function open(
    request: ArtistImportRequest,
    importArtist: ArtistImporter,
  ): Promise<ArtistImportOutcome> {
    const key = artistImportKey(
      request.provider,
      request.providerArtistId,
    );

    const remembered = known(request);

    if (remembered) {
      return Promise.resolve({ slug: remembered });
    }

    const running = inFlight.get(key);

    if (running) {
      return running;
    }

    const attempt = importArtist(request)
      .then((outcome) => {
        completed.set(key, outcome.slug);
        memory.write(key, outcome.slug);

        return outcome;
      })
      .finally(() => {
        // A settled attempt leaves the room, whether it worked or not, so
        // the next open is a new try rather than the old failure.
        inFlight.delete(key);
      });

    inFlight.set(key, attempt);

    return attempt;
  }

  return { known, open };
}

/**
 * The pool every import address shares.
 *
 * Module level on purpose: it is what makes a double mount of the page, or a
 * second visit while the first import is still running, join that import
 * instead of starting another one.
 */
export const sharedArtistImportPool = createArtistImportPool();
