'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { artistAPI } from '../../lib/api';
import Input from '../../../components/ui/Input';
import Button from '../../../components/ui/Button';
import ArtistCard from '../../../components/ArtistCard';
import LoadingState from '../../../components/LoadingState';

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

export default function ArtistsPage() {
  const t = useTranslations('artists');
  const params = useParams();
  const router = useRouter();
  const locale = (params?.locale as string) || 'en';

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

      setArtists(await artistAPI.searchArtists(trimmedQuery));
    } catch {
      setArtists([]);
      setError(t('searchError'));
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
        router.push(`/${locale}/artists/${artist.slug}`);
        return;
      }

      setImportingArtistId(artist.provider_artist_id);

      const importedArtist = await artistAPI.importArtist(
        artist.provider_artist_id,
        artist.provider,
        {
          name: artist.name,
          image: artist.image,
          genres: artist.genres
        }
      );

      if (!importedArtist?.slug) {
        throw new Error('Import did not return a slug.');
      }

      router.push(`/${locale}/artists/${importedArtist.slug}`);
      router.refresh();
    } catch (err) {
      // Surface the backend reason (e.g. no exact Songkick match)
      // instead of hiding it behind a generic message.
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? t('importError');

      setError(detail);
    } finally {
      setImportingArtistId(null);
    }
  }

  const isImporting = importingArtistId !== null;

  return (
    <div className="min-h-screen">
      <main className="mx-auto max-w-4xl px-4 py-8">
        <h1 className="mb-6 text-[28px] font-bold">{t('searchTitle')}</h1>

        <form onSubmit={searchArtists} className="mb-8">
          <div className="flex gap-3">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('searchPlaceholder')}
              className="flex-1"
              disabled={isImporting}
            />

            <Button type="submit" disabled={searchLoading || isImporting}>
              {searchLoading ? t('searching') : t('search')}
            </Button>
          </div>
        </form>

        {error && (
          <div
            role="alert"
            className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
          >
            {error}
          </div>
        )}

        {searchLoading && <LoadingState message={t('searching')} />}

        {!searchLoading && isImporting && (
          <LoadingState message={t('importing')} />
        )}

        {!searchLoading &&
          !isImporting &&
          artists.length === 0 &&
          query.trim() &&
          !error && (
            <div className="py-16 text-center">
              <p className="text-gray-400">{t('noSearchResults')}</p>
            </div>
          )}

        {!searchLoading && (
          <div
            className={`grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 ${
              isImporting ? 'pointer-events-none opacity-60' : ''
            }`}
          >
            {artists.map((artist) => (
              <ArtistCard
                key={`${artist.provider}-${artist.provider_artist_id}`}
                artist={artist}
                basePath={`/${locale}`}
                onClick={() => selectArtist(artist)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}