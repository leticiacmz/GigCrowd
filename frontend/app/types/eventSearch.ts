/**
 * The events catalogue as a search result.
 *
 * A search row is not the full event response: enough to say what an event is,
 * when it is, where it is and who is on, without assembling attendance,
 * provenance and a festival block per row that a list would never read.
 */
export interface EventSearchVenue {
  slug?: string | null;
  name?: string | null;
  city?: string | null;
  country?: string | null;
}

export interface EventSearchArtist {
  slug: string;
  name?: string | null;
  image?: string | null;
  genres?: string[];
}

export interface EventSearchFestival {
  name?: string | null;
  series_id: string;
}

/** Where the next page starts. Opaque; pass it straight back. */
export interface EventSearchCursor {
  date: string;
  id: string;
}

export interface EventSearchRow {
  id: string;
  title: string;
  starts_at?: string | null;
  ends_at?: string | null;
  event_type?: string | null;
  location?: { city?: string | null; country?: string | null } | null;
  venue?: EventSearchVenue | null;
  artists: EventSearchArtist[];
  festival?: EventSearchFestival | null;
}

export interface EventSearchResponse {
  events: EventSearchRow[];
  total: number;
  next_cursor?: EventSearchCursor | null;
  genre?: string | null;
}

/**
 * One genre in the catalogue, with how many artists carry it.
 *
 * The count comes from artist metadata. Genres are never inferred from an event
 * title, because titles contain places and festival names as often as they
 * contain genres.
 */
export interface EventSearchGenre {
  name: string;
  artists: number;
}
