'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import { artistAPI } from '../lib/api';

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
      <header className="border-b border-gray-800 px-4 py-4">
        <div className="max-w-6xl mx-auto flex justify-between">
          <Link href="/feed" className="text-2xl font-bold">
            GigCrowd
          </Link>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-6">
          Search artists
        </h1>

        <form onSubmit={searchArtists} className="mb-8">
          <div className="flex gap-3">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search on Spotify..."
              className="flex-1 px-4 py-3 rounded-lg bg-gray-900 border border-gray-700"
            />

            <button className="px-6 rounded-lg bg-purple-600">
              {loading ? 'Searching...' : 'Search'}
            </button>
          </div>
        </form>

        <div className="space-y-4">
          {artists.map((artist) => (
            <button
              key={artist.provider_artist_id}
              onClick={() => selectArtist(artist)}
              className="w-full text-left bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-purple-500"
            >
              <div className="flex gap-4 items-center">
                {artist.image && (
                  <img
                    src={artist.image}
                    alt={artist.name}
                    className="w-16 h-16 rounded-full object-cover"
                  />
                )}

                <div>
                  <h2 className="text-xl font-semibold">
                    {artist.name}
                  </h2>

                  <p className="text-gray-400">
                    {artist.genres?.join(' • ')}
                  </p>

                  {artist.followers && (
                    <p className="text-gray-400">
                      {artist.followers.toLocaleString()} followers
                    </p>

                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      </main>
    </div>
  );
}
