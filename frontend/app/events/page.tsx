'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import { artistAPI } from '../lib/api';
import Input from '../../components/ui/Input';
import Button from '../../components/ui/Button';
import ArtistCard from '../../components/ArtistCard';

interface ArtistSearchResult {
  provider: string;
  provider_artist_id: string;
  name: string;
  followers?: number;
  popularity?: number;
  image?: string;
  genres?: string[];
  is_imported: boolean;
  slug?: string;
  id?: string;
}

export default function EventsPage() {
  const router = useRouter();

  const [query, setQuery] = useState('');
  const [artists, setArtists] = useState<ArtistSearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  async function searchArtists(e: React.FormEvent) {
    e.preventDefault();

    if (!query.trim()) return;

    try {
      setLoading(true);

      const result = await artistAPI.searchArtists(query);

      setArtists(result);
    } finally {
      setLoading(false);
    }
  }

  async function selectArtist(artist: ArtistSearchResult) {
    let target = artist;

    if (!artist.is_imported) {
      target = await artistAPI.importArtist(
        artist.provider_artist_id
      );
    }

    if (target.slug) {
      router.push(`/artists/${target.slug}`);
    }
  }

  return (
    <div className="min-h-screen">
      <main className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-[28px] font-bold mb-6">
          Search artists
        </h1>

        <form onSubmit={searchArtists} className="mb-8">
          <div className="flex gap-3">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search on Spotify..."
              className="flex-1"
            />
            <Button type="submit" disabled={loading}>
              {loading ? 'Searching...' : 'Search'}
            </Button>
          </div>
        </form>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {artists.map((artist) => (
            <div key={artist.provider_artist_id} onClick={() => selectArtist(artist)}>
              <ArtistCard artist={artist} />
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
