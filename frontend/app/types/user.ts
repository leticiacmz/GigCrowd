export interface User {
  id: string;

  username: string;

  email: string;

  full_name?: string;

  avatar_url?: string;

  bio?: string;

  location?: string;

  role: string;

  created_at?: string;

  followers_count: number;

  following_count: number;
}


export interface UserStats {

  username: string;

  followers_count: number;

  following_count: number;

  bio?: string;

  avatar_url?: string;


  shows_attended: number;

  shows_going: number;

  shows_maybe: number;

  artists_seen: number;

  upcoming_events: number;

  total_posts: number;
}