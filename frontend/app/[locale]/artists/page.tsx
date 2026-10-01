'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { artistAPI } from '../../lib/api';
import { Artist } from '../../types/artist';

import ArtistCard from '../../../components/ArtistCard';
import LoadingState from '../../../components/LoadingState';
import EmptyState from '../../../components/EmptyState';

export default function ArtistsPage() {
  const t = useTranslations('artists');
  const params = useParams();
  const locale = (params?.locale as string) || 'en';

  const [artists, setArtists] = useState<Artist[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function loadArtists() {
      try {
        setLoading(true);
        setError('');

        const data = await artistAPI.getArtists();

        if (cancelled) {
          return;
        }

        setArtists(
          [...data].sort((a, b) => a.name.localeCompare(b.name))
        );
      } catch {
        if (!cancelled) {
          setError(t('loadError'));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadArtists();

    return () => {
      cancelled = true;
    };
  }, [t]);

  const groupedArtists = useMemo(() => {
    return artists.reduce<Record<string, Artist[]>>((groups, artist) => {
      const letter = artist.name.charAt(0).toUpperCase() || '#';

      if (!groups[letter]) {
        groups[letter] = [];
      }

      groups[letter].push(artist);

      return groups;
    }, {});
  }, [artists]);

  const letters = Object.keys(groupedArtists).sort();

  return (
    <div className="min-h-screen">
      <main className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="mb-8 text-[28px] font-bold">{t('title')}</h1>

        {error && (
          <div
            role="alert"
            className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
          >
            {error}
          </div>
        )}

        {loading ? (
          <LoadingState message={t('loadingArtists')} />
        ) : artists.length === 0 ? (
          <EmptyState
            icon="🎵"
            title={t('noArtistsFound')}
            description={t('emptyDescription')}
          />
        ) : (
          <div className="space-y-10">
            {letters.map((letter) => (
              <section key={letter}>
                <h2 className="mb-4 text-[24px] font-bold text-secondary">
                  {letter}
                </h2>

                <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
                  {groupedArtists[letter].map((artist) => (
                    <ArtistCard
                      key={artist.slug || artist.provider_artist_id}
                      artist={artist}
                      basePath={`/${locale}`}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}