export interface Artist {

  id?: string;

  provider: string;

  provider_artist_id: string;

  name: string;

  followers?: number;

  image?: string;

  genres: string[];

  verified: boolean;

  is_imported: boolean;

  slug?: string;

}