export type NotificationType = 'follow' | 'like' | 'comment' | 'reply';

/** Where a notification should take the user when they act on it. */
export interface NotificationTarget {
  kind: 'community_post' | 'comment' | 'artist' | 'event' | 'profile';
  id: string;
  artist_slug?: string | null;
  /** Display name for artist targets. */
  name?: string | null;
  /** Title of an event target. */
  title?: string | null;
  starts_at?: string | null;
  username?: string | null;
  excerpt?: string | null;
}

export interface NotificationActor {
  id: string;
  username: string | null;
  avatar_url?: string | null;
}

export interface Notification {
  id: string;
  type: NotificationType;
  read: boolean;
  created_at: string;
  related_entity_type: string | null;
  related_entity_id: string | null;
  context: {
    artist_slug?: string | null;
    artist_name?: string | null;
    post_id?: string | null;
    comment_id?: string | null;
    excerpt?: string | null;
    username?: string | null;
  };
  actor: NotificationActor;
  target: NotificationTarget | null;
}
