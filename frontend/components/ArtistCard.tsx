import Link from 'next/link';

import Avatar from './ui/Avatar';
import Badge from './ui/Badge';

interface ArtistCardProps {
  artist: {
    slug?: string;
    provider_artist_id?: string;
    name: string;
    image?: string;
    genres?: string[];
  };
  /**
   * Where the card leads. Callers that know the right destination - an
   * artist's page here, or their import address when GigCrowd does not hold
   * them yet - say so; otherwise the card falls back to the artist page path.
   */
  href?: string;
  /** Locale-aware path prefix, e.g. "/pt-BR". */
  basePath?: string;
}

export default function ArtistCard({
  artist,
  href,
  basePath = '',
}: ArtistCardProps) {
  const target =
    href ?? `${basePath}/artists/${artist.slug || artist.provider_artist_id}`;

  return (
    <Link
      href={target}
      className="block"
    >
      <div className="bg-card-bg border border-border rounded-xl overflow-hidden hover:border-accent hover:bg-card-hover transition-all duration-200 cursor-pointer">
        <div className="aspect-square relative">
          {artist.image ? (
            <img
              src={artist.image}
              alt={artist.name}
              className="w-full h-full object-contain"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center bg-card-hover text-6xl">
              🎵
            </div>
          )}
        </div>

        <div className="p-4">
          <h3 className="text-foreground font-semibold text-lg mb-2 line-clamp-1">
            {artist.name}
          </h3>

          {artist.genres && artist.genres.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {artist.genres.slice(0, 2).map((genre, index) => (
                <Badge key={index} variant="outline" size="sm">
                  {genre}
                </Badge>
              ))}

              {artist.genres.length > 2 && (
                <Badge variant="outline" size="sm">
                  +{artist.genres.length - 2}
                </Badge>
              )}
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}
