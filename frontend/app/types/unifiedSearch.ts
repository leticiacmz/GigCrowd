import type {
  EventSearchCursor,
  EventSearchRow,
} from './eventSearch';

/**
 * One artist as the search box sees it.
 *
 * Two things decide what happens next, and both come from the same row:
 * `is_imported` says whether GigCrowd already holds the act, and `slug` is
 * where an act that is already here opens. An act without them is a Songkick
 * result waiting to be imported - which only happens if the reader picks it.
 */
export interface ArtistSearchResult {
  provider: string;
  provider_artist_id: string;
  name: string;
  followers?: number;
  image?: string;
  genres?: string[];
  is_imported: boolean;
  slug?: string;
  id?: string;
}

/**
 * The answer to one general query, in both of the ways this app can answer it.
 *
 * The type of a result is read from where it sits rather than declared on each
 * row: `artists` holds acts, `events` holds shows, and a show carrying a
 * `festival` block is a festival edition. There is no venue list, because
 * GigCrowd has no venue page to open - a venue query is answered with the
 * events that mention it, and nothing more is implied.
 *
 * `artists_unavailable` is not the same answer as an empty `artists`: it says
 * the artist half was asked for and could not be reached, so the page can say
 * so instead of showing "no artists found" as a fact.
 */
export interface UnifiedSearchResponse {
  query: string;
  artists: ArtistSearchResult[];
  artists_unavailable: boolean;
  events: EventSearchRow[];
  total: number;
  next_cursor?: EventSearchCursor | null;
  genre?: string | null;
}
