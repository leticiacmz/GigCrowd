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

/** The figures a profile header shows, each counted from its collection. */
export interface ProfileStats {
  followers_count: number;
  following_count: number;
  shows_attended: number;
  shows_going: number;
  shows_maybe: number;
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