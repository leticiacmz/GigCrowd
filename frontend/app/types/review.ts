/**
 * A review of a show the user attended.
 *
 * The shape is shared by the editor that writes one, the card that reads one and
 * the profile that lists them, so a review is described in exactly one place.
 */

/** The body accepted when a review is written on its own. */
export interface ReviewPayload {
  /** 1 to 5 stars. Always required: a rating is the point of a review. */
  rating: number;

  /** Optional free text. */
  review?: string | null;

  /** Optional photo of the show, hosted by the project's media service. */
  photo_url?: string | null;

  /** The media service's handle for that photo, so it can be replaced. */
  photo_public_id?: string | null;
}

/** A review, as the API returns it on a show log. */
export interface ShowLog {
  id: string;
  event_id: string;
  status: 'going' | 'maybe' | 'went';
  rating?: number | null;
  review?: string | null;
  photo_url?: string | null;
  photo_public_id?: string | null;
  date?: string | null;
  reviewed_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

/** An image stored by the media service. */
export interface UploadedImage {
  public_id: string;
  url: string;
  width?: number;
  height?: number;
  bytes?: number;
  format?: string;
}