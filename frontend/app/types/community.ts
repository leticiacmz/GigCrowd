/**
 * Shapes returned by the artist-scoped community API.
 *
 * The backend inlines the author's `username` and `user_avatar_url` on every
 * post, comment and reply, so the UI can link to a profile without issuing a
 * request per author.
 */
export interface CommunityPost {
  id: string;
  artist_slug: string;
  user_id: string;
  content: string;
  image_url?: string | null;
  likes_count: number;
  comments_count: number;
  created_at: string;
  username?: string | null;
  user_avatar_url?: string | null;
  liked_by_user: boolean;
}

export interface CommunityComment {
  id: string;
  post_id: string;
  user_id: string;
  content: string;
  parent_comment_id?: string | null;
  created_at: string;
  updated_at?: string | null;
  username?: string | null;
  user_avatar_url?: string | null;
  replies: CommunityComment[];
  replies_count: number;
}

/**
 * What a visitor is allowed to do in this artist's community.
 *
 * `signed-out` and `non-follower` both have read access only; they differ in
 * the call to action shown, and only `signed-out` may be sent to sign in.
 */
export type ParticipationLevel = 'follower' | 'non-follower' | 'signed-out';
