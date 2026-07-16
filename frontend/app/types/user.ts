export interface UserProfile {

  id: string;

  username: string;

  email?: string;

  full_name?: string;

  avatar_url?: string;

  bio?: string;

  location?: string;

  followers_count: number;

  following_count: number;

  created_at?: string;

}