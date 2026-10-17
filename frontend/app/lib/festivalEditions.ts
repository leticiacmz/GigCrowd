/*
  Filtering a festival's editions by country - never by anything else.

  A series can span countries: the local catalogue's Lollapalooza holds
  editions in Brazil, Argentina, Chile and France, and a reader looking for
  the one near them should not have to scan every year to find it. The filter
  is built from what the response already carries - the edition's own
  location, or the venue's when the event itself has none - and from nothing
  else. An edition whose country was never recorded is not assigned one: it
  is listed under "all", and never under a specific country, because guessing
  where someone's ticket was would state something the data does not.
*/

/** The fields the question can be answered from, on an edition's event. */
export interface EditionCountrySource {
  location?: { country?: string | null } | null;
  venue?: { country?: string | null } | null;
}

/** The value that keeps every edition listed. */
export const ALL_COUNTRIES = 'all';

/**
 * The country an edition actually states, or null when it states none.
 *
 * The event's own location is read first and the venue is the fallback, the
 * same precedence the address line on every edition row uses.
 */
export function editionCountry(
  event: EditionCountrySource,
): string | null {
  const country = event.location?.country || event.venue?.country;

  if (!country) {
    return null;
  }

  const trimmed = country.trim();

  return trimmed || null;
}

/** The distinct countries present among these editions, sorted. */
export function editionCountries(
  events: EditionCountrySource[],
): string[] {
  const found = new Set<string>();

  for (const event of events) {
    const country = editionCountry(event);

    if (country) {
      found.add(country);
    }
  }

  return Array.from(found).sort((a, b) => a.localeCompare(b));
}

/** Whether an edition belongs under the selected country. */
export function matchesCountry(
  event: EditionCountrySource,
  country: string,
): boolean {
  if (country === ALL_COUNTRIES) {
    return true;
  }

  return editionCountry(event) === country;
}
