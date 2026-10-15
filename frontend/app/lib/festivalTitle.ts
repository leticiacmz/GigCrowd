/*
  How a festival's name is presented - never how it is stored.

  Songkick titles a festival date from the artist's page ("Demi Lovato Rock
  In Rio 2022") and names an edition "Festival @ Venue". A header that naively
  composes "artist @ name" then reads "Demi Lovato @ Demi Lovato Rock In Rio
  2022" or stacks two "@" signs. These functions fix the *presentation*:

  * the stored name is a value, never an input to rewrite - it is returned
    verbatim or not used at all;
  * a stored festival name wins over the event title, as it is what the
    importer recorded the festival to be called;
  * the artist prefix is added only when it adds information - it is skipped
    when the name already contains the artist, and when the name already
    reads as a full "Name @ Venue" descriptor (dropping the venue to make
    room for the artist would lose a real part of the name);
  * the title is a fallback, and only after the leading artist prefix is
    stripped from it.

  The same rules apply on the event detail header, its festival card, and
  anywhere else these helpers are reached, so the pages cannot drift apart.
*/

export interface FestivalNameSource {
  /** The stored festival block's name, when the importer recorded one. */
  festivalName?: string | null;
  /** The event's stored title - a fallback candidate only. */
  title?: string | null;
  /** The display name of the event's principal linked artist. */
  artistName?: string | null;
}

/**
 * The event title without its leading artist prefix, when it has one.

 * "Demi Lovato Rock In Rio 2022" is how Songkick titles the artist's own
 * appearance page, so the artist's name at the front of it says nothing
 * about the festival. A title that is nothing but the artist's name strips
 * to an empty string, which callers read as "no name here".
 */
export function stripArtistPrefix(
  title?: string | null,
  artistName?: string | null,
): string {
  const trimmedTitle = title?.trim() ?? '';
  const artist = artistName?.trim() ?? '';

  if (!trimmedTitle || !artist) return trimmedTitle;

  if (trimmedTitle.toLowerCase().startsWith(artist.toLowerCase())) {
    return trimmedTitle.slice(artist.length).trim();
  }

  return trimmedTitle;
}

/**
 * The festival's display name: the stored name when there is one, otherwise
 * the event title after the artist prefix is stripped, otherwise nothing.
 */
export function festivalDisplayName(
  source: FestivalNameSource,
): string {
  const stored = source.festivalName?.trim();
  if (stored) return stored;

  return stripArtistPrefix(source.title, source.artistName);
}

/**
 * The event header title: the artist at the festival, without ever saying
 * the artist twice or stacking two "@" signs.
 *
 * The artist is prefixed to the festival name only when the prefix adds
 * something: a name that already contains the artist ("Demi Lovato @ Barra
 * Olympic Park" for an artist named Demi Lovato) or a name that already
 * reads as a complete "Festival @ Venue" descriptor is shown as it is. With
 * no festival name to show, the artist alone carries the header, and with
 * no artist the name does - the stored title remains the last resort.
 */
export function eventDisplayTitle(
  source: FestivalNameSource,
): string {
  const artist = source.artistName?.trim() ?? '';
  const name = festivalDisplayName(source);
  const original = source.title?.trim() ?? '';

  if (!artist) return name || original;
  if (!name) return artist || original;

  const lowerName = name.toLowerCase();

  // The name already says who the artist is, or already reads as a complete
  // "Name @ Venue" - prefixing would repeat the artist or stack a second "@".
  if (lowerName.includes(artist.toLowerCase())) return name;
  if (lowerName.includes('@')) return name;

  return `${artist} @ ${name}`;
}
