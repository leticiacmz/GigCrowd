/*
  The canonical address of a festival: its series.

  A festival is addressed two ways and both reach the same page: by one of
  its dates (`/festivals/{eventId}`) or by the series it is
  (`/festivals/series/{seriesId}`). The series address is the one to share -
  it names the festival, not a night - and the two never collide because a
  series id is numeric while a date-keyed id is a 24-character object id.

  This module answers the questions the routing asks: which of the two a
  parameter-shaped value really is, what the canonical link to a festival's
  page is from an event, and which edition a fetch should open on.
*/

/** How a `/festivals/series/{value}` parameter should be read. */
export type FestivalSeriesRoute =
  | { kind: 'series'; seriesId: string }
  | { kind: 'legacy-event'; eventId: string }
  | { kind: 'invalid' };

/**
 * A stored event's own id. Series ids are the short numeric ones Songkick
 * issues; only an id shaped like this application's own records is worth
 * asking the backend about.
 */
const EVENT_ID = /^[0-9a-f]{24}$/i;

const SERIES_ID = /^\d+$/;

/**
 * Which route a `/festivals/series/{value}` parameter belongs to.
 *
 * The two shapes are told apart by form alone, never by lookup: a series id
 * is numeric, an event id is a 24-character hexadecimal object id, and a
 * value that is neither names no festival this server can show. An all-digit
 * object id is still an object id - Songkick's series ids are far shorter -
 * so the object-id check leads.
 */
export function resolveFestivalSeriesParam(
  value: string | null | undefined,
): FestivalSeriesRoute {
  const text = (value ?? '').trim();

  if (EVENT_ID.test(text)) {
    return { kind: 'legacy-event', eventId: text };
  }

  if (SERIES_ID.test(text)) {
    return { kind: 'series', seriesId: text };
  }

  return { kind: 'invalid' };
}

/**
 * The canonical festival link for an event that states its series.
 *
 * The link names the festival and marks the event as the edition to open on,
 * so the address stays the festival's own when a reader shares it - and the
 * backend still shows this event's own lineup. The path keeps the
 * `/{locale}/festivals/` prefix every festival address has.
 */
export function festivalSeriesHref(
  locale: string,
  seriesId: string,
  editionEventId: string,
): string {
  return `/${locale}/festivals/series/${seriesId}?edition=${editionEventId}`;
}

/**
 * The edition named by `?edition=`, when it names a stored event.
 *
 * Only an id shaped like this application's own event records is sent along;
 * anything else falls back to the default selection rather than being handed
 * to the backend as a question about a record that cannot exist.
 */
export function festivalEditionFromSearch(
  search: string
): string | null {
  const match = /[?&]edition=([^&#]*)/.exec(search);

  if (!match) {
    return null;
  }

  let value = match[1];

  try {
    value = decodeURIComponent(value);
  } catch {
    // A query string that is not even valid percent-encoding names nothing.
    return null;
  }

  return EVENT_ID.test(value) ? value : null;
}
