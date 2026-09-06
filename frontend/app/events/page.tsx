'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

import { artistAPI } from '../lib/api';
import Input from '../../components/ui/Input';
import Button from '../../components/ui/Button';
import ArtistCard from '../../components/ArtistCard';
import LoadingState from '../../components/LoadingState';

interface ArtistSearchResult {
  provider: string;
  provider_artist_id: string;
  name: string;
  followers?: number;
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
  const [searchLoading, setSearchLoading] = useState(false);
  const [importingArtistId, setImportingArtistId] = useState<string | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);

  async function searchArtists(e: React.FormEvent) {
    e.preventDefault();

    const trimmedQuery = query.trim();

    if (!trimmedQuery) {
      return;
    }

    try {
      setSearchLoading(true);
      setError(null);

      const result = await artistAPI.searchArtists(trimmedQuery);

      setArtists(result);
    } catch (err) {
      console.error('Failed to search artists:', err);

      setArtists([]);
      setError('Unable to search artists. Please try again.');
    } finally {
      setSearchLoading(false);
    }
  }

  async function selectArtist(artist: ArtistSearchResult) {
    if (importingArtistId) {
      return;
    }

    try {
      setError(null);

      if (artist.is_imported && artist.slug) {
        router.push(`/artists/${artist.slug}`);
        return;
      }

      setImportingArtistId(artist.provider_artist_id);

      const importedArtist = await artistAPI.importArtist(
        artist.provider_artist_id,
        artist.provider,
        artist
      );

      if (!importedArtist?.slug) {
        throw new Error('Artist was imported but no slug was returned.');
      }

      router.push(`/artists/${importedArtist.slug}`);
      router.refresh();
    } catch (err) {
      console.error('Failed to import artist:', err);

      setError(
        'Unable to import this artist. Please try again.'
      );
    } finally {
      setImportingArtistId(null);
    }
  }

  const isImporting = importingArtistId !== null;

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
              placeholder="Search artists..."
              className="flex-1"
              disabled={isImporting}
            />

            <Button
              type="submit"
              disabled={searchLoading || isImporting}
            >
              {searchLoading ? 'Searching...' : 'Search'}
            </Button>
          </div>
        </form>

        {error && (
          <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {searchLoading && (
          <LoadingState message="Searching artists..." />
        )}

        {!searchLoading && isImporting && (
          <LoadingState message="Importing artist and syncing events..." />
        )}

        {!searchLoading && !isImporting && artists.length === 0 && query.trim() && !error && (
          <div className="py-16 text-center">
            <p className="text-gray-400">
              No artists found.
            </p>
          </div>
        )}

        {!searchLoading && (
          <div
            className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 ${
              isImporting ? 'pointer-events-none opacity-60' : ''
            }`}
          >
            {artists.map((artist) => (
              <ArtistCard
                key={`${artist.provider}-${artist.provider_artist_id}`}
                artist={artist}
                onClick={() => selectArtist(artist)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
