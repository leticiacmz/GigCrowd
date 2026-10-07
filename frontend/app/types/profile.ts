/**
 * The concert half of a profile.
 *
 * A profile is not a row of counters: it is the shows someone went to, what
 * they said about them, the festivals they have been to and the artists they
 * follow. These types mirror the backend schemas of the same name, so the page
 * never has to guess a field name or a nullability.
 */

/** One festival a user has been to, with its editions collapsed together. */
export interface ProfileFestival {
  /** Stable identity of the festival series. */
  key: string;

  name: string;

  /** The newest edition the user logged, so the row can link to it. */
  event_id?: string | null;

  /** Distinct editions the user attended. */
  editions_count: number;

  /** Shows the user logged for this festival. */
  shows_count: number;

  first_date?: string | null;

  last_date?: string | null;

  image_url?: string | null;
}

/** One event from a user's show log, with the event it refers to. */
export interface ProfileEvent {
  event_id: string;
  title: string;
  starts_at?: string | null;
  ends_at?: string | null;
  event_type: string;
  venue_slug?: string | null;
  venue_name?: string | null;
  city?: string | null;
  country?: string | null;
  artist_slugs: string[];
  artist_names: string[];
  status?: string | null;
  festival?: ProfileFestival | null;

  /**
   * Whether this show carries the person's own opinion of it.
   *
   * A show log becomes a review by carrying one, so this marks the difference
   * between a night someone remembers attending and a night they wrote about.
   */
  has_review?: boolean;

  rating?: number | null;
}

/**
 * The three states a show can be in on someone's profile.
 *
 * These are the values the show log has always persisted, so the breakdown is a
 * way of reading one collection rather than a second attendance system. A
 * person has one log per show, so the three counts always add up to the number
 * of shows they have logged.
 */
export type ProfileShowStatus = 'attended' | 'want-to-go' | 'maybe';

/** The figures behind the breakdown, one per state. */
export type ProfileShowCounts = Record<ProfileShowStatus, number>;

/**
 * One state of a user's shows.
 *
 * `total` is how many rows that state holds and `counts` carries all three, so
 * the breakdown and the list are always read from the same answer and cannot
 * disagree with each other.
 */
export interface ProfileEventsResponse {
  username: string;
  events: ProfileEvent[];
  total: number;
  status?: ProfileShowStatus | null;
  counts: ProfileShowCounts;
  limit: number;
  skip: number;
}

/**
 * Where the next page of a show history starts.
 *
 * Opaque by design: the client passes it back exactly as the server produced it.
 * Reading the date out of it and composing a new one is how a paging scheme
 * quietly starts skipping rows on the days that have several.
 */
export interface ProfileEventCursor {
  date: string;
  id: string;
}

/**
 * One page of a user's show history.
 *
 * Same rows and same states as `ProfileEventsResponse`; only the way the next page
 * is addressed differs. `next_cursor` is null on the last page, which is how the
 * client knows to stop rather than asking for the same rows again.
 */
export interface ProfileEventsPageResponse {
  username: string;
  events: ProfileEvent[];
  total: number;
  status?: ProfileShowStatus | null;
  counts: ProfileShowCounts;
  limit: number;
  next_cursor?: ProfileEventCursor | null;
}

/**
 * One month of days on which this user went to a show.
 *
 * Only shows logged as `went` appear. A day with two festivals in one room carries
 * a count of two rather than a single mark.
 */
export interface ProfileShowCalendarResponse {
  username: string;
  year: number;
  month: number;
  days: Record<string, number>;
  total: number;
  has_any: boolean;
}

/** One calendar year and how many shows were attended in it. */
export interface ProfileShowYear {
  year: number;
  shows: number;
}

/**
 * The years a profile has attended shows in, newest first.
 *
 * Exists so the calendar's year selector can offer the years somebody actually
 * has. Without it the only way back to 2021 is the next-month arrow, sixty times
 * over, which is not navigation.
 */
export interface ProfileShowYearsResponse {
  username: string;
  years: ProfileShowYear[];
  current_year: number;
  has_any: boolean;
}

/** A review: an attended show that carries an opinion about it. */
export interface ProfileReview extends ProfileEvent {
  rating: number;
  review?: string | null;
  photo_url?: string | null;
  reviewed_at?: string | null;
}

/**
 * An artist the user follows.
 *
 * Following an artist is what puts someone in that artist's community, so the
 * row carries the community's activity alongside the artist's own details.
 */
export interface ProfileArtist {
  slug: string;
  name: string;
  image?: string | null;
  genres: string[];
  followers_count: number;
  posts_count: number;
  is_following: boolean;
}

/**
 * An artist this person has actually seen.
 *
 * The single figure here is the point of the section: how many distinct shows
 * they attended where this artist performed. It is deliberately the only number,
 * because a follower count or a community post count answers a different
 * question and would make a concert history read as a popularity chart.
 */
export interface ProfileSeenArtist {
  slug: string;
  name: string;
  image?: string | null;

  /** Distinct attended events where this artist performed. */
  shows_count: number;

  /**
   * Whether an imported artist page exists. An artist without one is still
   * listed - the person did see them - but the row must not link to a page that
   * does not exist.
   */
  resolved: boolean;
}

/**
 * Artists I have seen, most seen first.
 *
 * This is attendance, not intention: an artist the person merely follows is not
 * here unless they have been to a show. A festival contributes the performers
 * of the concrete date they attended, not every edition of that festival.
 */
export interface ProfileArtistsSeenResponse {
  username: string;
  artists: ProfileSeenArtist[];
  total: number;
}

/** The figures a profile header shows, each counted from its collection. */
export interface ProfileStats {
  followers_count: number;
  following_count: number;
  shows_attended: number;
  shows_going: number;
  shows_maybe: number;

  /**
   * Distinct artists this person has been to a show of.
   *
   * This is what the header shows under "Artists". It is not the number of
   * artists they follow: following is an intention, and this section is a
   * history.
   */
  artists_seen: number;
  upcoming_events: number;
  total_posts: number;
  reviews_count: number;
  festivals_count: number;
  followed_artists_count: number;
}

/** A profile's public details. */
export interface UserProfile {
  username: string;
  email?: string;
  full_name?: string | null;
  bio?: string | null;
  location?: string | null;
  avatar_url?: string | null;
  created_at: string;
}