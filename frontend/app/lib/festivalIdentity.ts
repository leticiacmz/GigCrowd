/*
  Whether a festival page exists for an event - the client's mirror of the
  backend rule.

  The backend opens a festival page only when a festival identity is
  confirmed: a Songkick series id read from structured source data - the
  stored festival block's own `series_id`, the block's URL, or the event's
  own Songkick address. Without one the request is a 404, so a link rendered
  for such an event opens an error page and presents an association the data
  never stated.

  This module answers the same question from the fields the event response
  already carries, so the event page renders its festival links only when
  the page they point to will exist. It never decides identity from a name:
  two festivals can share a name across cities and years, and the id is the
  only thing that identifies one.
*/

/** The event fields the question can be answered from. */
export interface FestivalIdentitySource {
  festival?: {
    series_id?: string | null;
    name?: string | null;
    url?: string | null;
    official_url?: string | null;
  } | null;
  source?: {
    url?: string | null;
  } | null;
}

/**
 * Songkick addresses a concrete festival date as
 * `/festivals/{series_id}-{slug}/id/{event_id}-{slug}`: the series the
 * festival is, and the edition this date is. Only the series segment is
 * read here - it is the identity.
 */
const SERIES_PATH = /\/festivals\/(\d+)(?:-[^/?#]+)?/;

function seriesFromUrl(url: string | null | undefined): string | null {
  const match = SERIES_PATH.exec(url ?? '');
  return match ? match[1] : null;
}

/**
 * The confirmed festival series id of this event, or `null` when its own
 * data states none.
 *
 * The order mirrors the backend: the stored block's id, then the URLs the
 * block carries, then the event's own address - which states the series
 * even when no festival block was ever written beside the event.
 */
export function festivalSeriesId(
  source: FestivalIdentitySource,
): string | null {
  const stored = source.festival?.series_id;

  if (stored !== null && stored !== undefined) {
    const text = String(stored).trim();

    if (text) {
      return text;
    }
  }

  for (const candidate of [
    source.festival?.url,
    source.festival?.official_url,
    source.source?.url,
  ]) {
    const series = seriesFromUrl(candidate);

    if (series) {
      return series;
    }
  }

  return null;
}
