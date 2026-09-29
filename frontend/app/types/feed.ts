export type ActivityType =
  | 'user_followed_user'
  | 'user_followed_artist'
  | 'community_post_created'
  | 'event_attendance'
  | 'review_created'
  | 'comment_created'
  | 'reaction_created';


export type ActivityObjectType =
  | 'user'
  | 'artist'
  | 'community_post'
  | 'event'
  | 'review'
  | 'comment';


export interface FeedActor {

  id: string;

  username?: string;

  avatar_url?: string;

}


export interface FeedActivity {

  id: string;

  actor: FeedActor;

  activity_type: ActivityType;

  object_type: ActivityObjectType;

  object_id: string;

  target_type?: ActivityObjectType | null;

  target_id?: string | null;

  payload: {
    username?: string;
    artist_name?: string;
    artist_slug?: string;
    preview?: string;
    status?: string;
    event_title?: string;
    event_id?: string;
    rating?: number;
    [key: string]: any;
  };

  created_at: string;

}


export interface FeedPage {

  items: FeedActivity[];

  limit: number;

  skip: number;

  total: number;

  has_more: boolean;

  next_skip?: number | null;

}


export interface FeedParams {

  limit?: number;

  skip?: number;

  activity_type?: ActivityType[];

}
