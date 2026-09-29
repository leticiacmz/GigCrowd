'use client';

import {
  useEffect,
  useMemo,
  useState,
} from 'react';

import {
  useParams,
  useRouter,
} from 'next/navigation';

import Link from 'next/link';

import {
  artistAPI,
  eventAPI,
} from '../../lib/api';

import Card from '../../../components/ui/Card';
import LoadingState from '../../../components/LoadingState';


interface ArtistSummary {
  songkick_id?: string;
  slug: string;
  name: string;
  url?: string;
  image?: string | null;
}

interface Venue {
  slug?: string | null;
  name: string;
  city?: string | null;
  country?: string | null;
}

interface Festival {
  name?: string | null;
  edition?: string | null;
  url?: string | null;
  official_url?: string | null;
  artists?: ArtistSummary[];
}

interface Location {
  city?: string | null;
  country?: string | null;
}

interface FestivalEvent {
  id: string;
  title: string;
  event_type?: string;
  starts_at: string;
  ends_at?: string | null;
  venue?: Venue | null;
  venue_slug?: string | null;
  location?: Location | null;
  festival?: Festival | null;
}

export default function FestivalPage() {
  const router = useRouter();
  const params = useParams();
  const festivalId = params.id as string;

  const [event, setEvent] = useState<FestivalEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [loadingArtistSlug, setLoadingArtistSlug] = useState<string | null>(null);

  useEffect(() => {
    loadFestival();
  }, [festivalId]);

  async function loadFestival() {
    try {
      setLoading(true);

      const data = await eventAPI.getEvent(festivalId);

      if (data?.event_type !== 'FestivalInstance') {
        setEvent(null);
        return;
      }

      setEvent(data);
    } catch (error) {
      console.error('Failed loading festival', error);
      setEvent(null);
    } finally {
      setLoading(false);
    }
  }

  const lineup = useMemo(() => {
    return [...(event?.festival?.artists ?? [])].sort((a, b) =>
      a.name.localeCompare(b.name, 'pt-BR')
    );
  }, [event]);

  const filteredLineup = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    if (!normalizedQuery) {
      return lineup;
    }

    return lineup.filter((artist) =>
      artist.name.toLowerCase().includes(normalizedQuery)
    );
  }, [lineup, query]);

  function formatFestivalDate(value: string) {
    return new Intl.DateTimeFormat('pt-BR', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    }).format(new Date(value));
  }

  const startDate = event
    ? formatFestivalDate(event.starts_at)
    : '';

  const endDate =
    event?.ends_at &&
    new Date(event.ends_at).getTime() >
      new Date(event.starts_at).getTime()
      ? formatFestivalDate(event.ends_at)
      : null;

  async function handleArtistClick(artist: ArtistSummary) {
    if (!artist.slug || loadingArtistSlug) {
      return;
    }

    try {
      setLoadingArtistSlug(artist.slug);

      try {
        const existingArtist = await artistAPI.getArtist(artist.slug);

        if (existingArtist?.slug) {
          router.push(`/artists/${existingArtist.slug}`);
          return;
        }
      } catch (error) {
        // The artist is not imported under the Songkick slug yet.
      }

      if (!artist.songkick_id) {
        router.push(`/artists/${artist.slug}`);
        return;
      }

      const importedArtist = await artistAPI.importArtist(
        artist.songkick_id,
        'songkick',
        {
          name: artist.name,
          slug: artist.slug,
          image: artist.image,
          url: artist.url,
        }
      );

      if (importedArtist?.slug) {
        router.push(`/artists/${importedArtist.slug}`);
        return;
      }

      router.push(`/artists/${artist.slug}`);
    } catch (error) {
      console.error('Failed opening festival artist', error);
    } finally {
      setLoadingArtistSlug(null);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingState message="Loading festival..." />
      </div>
    );
  }

  if (!event || !event.festival) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="text-center">
          <p className="text-gray-400 mb-4">
            Festival not found.
          </p>

          <button
            type="button"
            onClick={() => router.back()}
            className="text-accent hover:text-accent/80 transition"
          >
            ← Go back
          </button>
        </div>
      </div>
    );
  }

  const festivalName = event.festival.name || event.title;
  const officialUrl = event.festival.official_url || null;

  return (
    <div className="min-h-screen">
      <main className="max-w-6xl mx-auto px-4 py-8">
        <Link
          href={`/events/${event.id}`}
          className="inline-flex items-center text-sm text-accent hover:text-accent/80 transition"
        >
          ← Back to event
        </Link>

        <section className="mt-6 rounded-2xl border border-border bg-card-bg p-6 md:p-8">
          <p className="text-xs uppercase tracking-wide text-accent mb-3">
            Festival
          </p>

          <h1 className="text-3xl md:text-5xl font-bold tracking-tight">
            {festivalName}
          </h1>

          <div className="mt-7 grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <p className="text-xs uppercase tracking-wide text-gray-500 mb-1">
                Dates
              </p>

              <p className="text-gray-200">
                {startDate}
                {endDate && <> — {endDate}</>}
              </p>
            </div>

            <div>
              <p className="text-xs uppercase tracking-wide text-gray-500 mb-1">
                Venue
              </p>

              <p className="text-gray-200">
                {event.venue?.name ||
                  event.venue_slug ||
                  'Venue unavailable'}
              </p>
            </div>

            <div>
              <p className="text-xs uppercase tracking-wide text-gray-500 mb-1">
                Location
              </p>

              <p className="text-gray-200">
                {event.location?.city || event.venue?.city || 'Unknown city'}
                {(event.location?.country || event.venue?.country) && (
                  <>
                    {' • '}
                    {event.location?.country || event.venue?.country}
                  </>
                )}
              </p>
            </div>
          </div>

          {officialUrl && (
            <div className="mt-7">
              <a
                href={officialUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center rounded-lg bg-accent px-5 py-3 text-sm font-semibold text-white hover:opacity-90 transition"
              >
                Official website ↗
              </a>
            </div>
          )}
        </section>

        <section className="mt-8">
          <Card className="p-6 md:p-8">
            <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-5">
              <div>
                <p className="text-xs uppercase tracking-wide text-accent mb-2">
                  Lineup
                </p>

                <h2 className="text-2xl font-bold">
                  {lineup.length > 0
                    ? `${lineup.length} artists`
                    : 'Artists'}
                </h2>
              </div>

              {lineup.length > 0 && (
                <div className="w-full md:w-72">
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search artists..."
                    className="w-full rounded-lg border border-border bg-background px-4 py-3 text-sm text-foreground outline-none focus:border-accent"
                  />
                </div>
              )}
            </div>

            {filteredLineup.length === 0 ? (
              <div className="py-16 text-center">
                <p className="text-gray-500">
                  {lineup.length === 0
                    ? 'The festival lineup is not available yet.'
                    : 'No artists match your search.'}
                </p>
              </div>
            ) : (
              <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {filteredLineup.map((artist) => {
                  const isLoading = loadingArtistSlug === artist.slug;

                  return (
                    <button
                      key={artist.songkick_id || artist.slug}
                      type="button"
                      onClick={() => handleArtistClick(artist)}
                      disabled={Boolean(loadingArtistSlug)}
                      className="group rounded-xl border border-border bg-background/20 p-4 text-left hover:border-accent hover:bg-card-hover transition disabled:opacity-60 disabled:cursor-wait"
                    >
                      <div className="flex items-center gap-4">
                        {artist.image ? (
                          <img
                            src={artist.image}
                            alt={artist.name}
                            className="h-14 w-14 rounded-full object-cover shrink-0"
                          />
                        ) : (
                          <div className="h-14 w-14 rounded-full bg-card-hover flex items-center justify-center text-xl shrink-0">
                            ♪
                          </div>
                        )}

                        <div className="min-w-0 flex-1">
                          <p className="font-semibold truncate group-hover:text-accent transition">
                            {artist.name}
                          </p>

                          <p className="text-xs text-gray-500 mt-1">
                            {isLoading ? 'Opening artist...' : 'Open artist'}
                          </p>
                        </div>

                        <span className="text-accent shrink-0">
                          →
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </Card>
        </section>
      </main>
    </div>
  );
}
