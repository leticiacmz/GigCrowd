'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { artistAPI, eventAPI } from '@/app/lib/api';
import { isAuthenticated } from '@/app/lib/auth';
import { useAuthAction } from '@/app/lib/use-auth-action';
import ArtistTabs from '@/components/artist/ArtistTabs';
import Badge from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import Card from '@/components/ui/Card';
import EventCard from '@/components/EventCard';
import LoadingState from '@/components/LoadingState';

interface ArtistProfile {
  id?: string;
  slug?: string;
  name: string;
  image?: string;
  genres: string[];
  followers_count?: number;
  events?: {
    upcoming: number;
    total: number;
  };
}

interface ArtistEvent {
  id: string;
  title: string;
  starts_at: string;
  ends_at?: string | null;
  event_type?: string;
  ticket_url?: string | null;
}

export default function ArtistProfilePage() {
  const params = useParams<{ locale: string; slug: string }>();
  const locale = params?.locale ?? 'en';
  const artistSlug = params?.slug ?? '';

  const t = useTranslations('artist');
  const tEvent = useTranslations('event');
  const tCommunity = useTranslations('community');

  const runAuthAction = useAuthAction({ locale });

  const [artist, setArtist] = useState<ArtistProfile | null>(null);
  const [events, setEvents] = useState<ArtistEvent[]>([]);
  const [relatedArtists, setRelatedArtists] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [relatedLoading, setRelatedLoading] = useState(false);
  const [error, setError] = useState('');
  const [following, setFollowing] = useState(false);
  const [followLoading, setFollowLoading] = useState(false);
  const [signedIn, setSignedIn] = useState(false);

  const loadArtist = useCallback(async () => {
    try {
      setLoading(true);
      setError('');

      const data = await artistAPI.getArtist(artistSlug);
      setArtist(data);
    } catch {
      setError(t('loadError'));
    } finally {
      setLoading(false);
    }
  }, [artistSlug, t]);

  const loadArtistEvents = useCallback(async () => {
    try {
      const data = await eventAPI.getArtistEvents(artistSlug);
      setEvents(
        [...data].sort(
          (a, b) =>
            new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime()
        )
      );
    } catch {
      setEvents([]);
    }
  }, [artistSlug]);

  const loadFollowStatus = useCallback(async () => {
    try {
      const data = await artistAPI.getFollowStatus(artistSlug);
      setFollowing(Boolean(data.following));
    } catch {
      setFollowing(false);
    }
  }, [artistSlug]);

  const loadRelatedArtists = useCallback(async () => {
    try {
      setRelatedLoading(true);
      const data = await artistAPI.getRelatedArtists(artistSlug);
      setRelatedArtists(data.related_artists || []);
    } catch {
      setRelatedArtists([]);
    } finally {
      setRelatedLoading(false);
    }
  }, [artistSlug]);

  useEffect(() => {
    if (!artistSlug) {
      return;
    }

    loadArtist();
    loadArtistEvents();

    // Follow status is only meaningful with a session; a signed-out visitor
    // still sees the whole public artist page.
    const active = isAuthenticated();
    setSignedIn(active);

    if (active) {
      loadFollowStatus();
    }
  }, [artistSlug, loadArtist, loadArtistEvents, loadFollowStatus]);

  useEffect(() => {
    if (artist) {
      loadRelatedArtists();
    }
  }, [artist, loadRelatedArtists]);

  const handleFollow = useCallback(async () => {
    setFollowLoading(true);

    try {
      if (following) {
        await artistAPI.unfollowArtist(artistSlug);
        setFollowing(false);
      } else {
        await artistAPI.followArtist(artistSlug);
        setFollowing(true);
      }
    } catch {
      // Leave the previous state in place; the next render shows the real value.
    } finally {
      setFollowLoading(false);
    }
  }, [artistSlug, following]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <LoadingState message={t('loadingArtist')} />
      </div>
    );
  }

  if (error || !artist) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4">
        <p className="text-center text-muted">{error || t('notFound')}</p>
        <Link
          href={`/${locale}/artists`}
          className="text-accent-text underline-offset-2 hover:underline"
        >
          {tEvent('backToArtists')}
        </Link>
      </div>
    );
  }

  const now = new Date();

  const upcomingEvents = events
    .filter((event) => {
      const end = event.ends_at ?? event.starts_at;
      return new Date(end).getTime() >= now.getTime();
    })
    .slice(0, 6);

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      <Card className="overflow-hidden p-0">
        {artist.image && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={artist.image}
            alt={artist.name}
            className="h-48 w-full object-cover sm:h-72"
          />
        )}

        <div className="p-5 sm:p-8">
          <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h1 className="text-3xl font-bold sm:text-4xl">{artist.name}</h1>

              {artist.followers_count !== undefined && (
                <p className="mt-1 text-sm text-muted">
                  {artist.followers_count} {t('followers')}
                </p>
              )}
            </div>

            <Button
              onClick={() => runAuthAction(handleFollow)}
              disabled={followLoading}
              variant={following ? 'outline' : 'primary'}
              className="shrink-0"
            >
              {followLoading
                ? t('loadingRelated')
                : following
                  ? t('following')
                  : t('follow')}
            </Button>
          </div>

          {artist.genres?.length > 0 && (
            <div className="mb-6">
              <h2 className="mb-2 text-sm font-medium text-muted">
                {t('genres')}
              </h2>
              <div className="flex flex-wrap gap-2">
                {artist.genres.map((genre) => (
                  <Badge key={genre} variant="outline">
                    {genre}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          <ArtistTabs locale={locale} slug={artistSlug} active="overview" />
        </div>
      </Card>

      <div className="mt-6 flex flex-col gap-8">
        <section aria-labelledby="upcoming-events-heading">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2
              id="upcoming-events-heading"
              className="text-xl font-bold sm:text-2xl"
            >
              {t('upcomingEvents')}
            </h2>

            {(artist.events?.total ?? 0) > 6 && (
              <Link
                href={`/${locale}/artists/${artistSlug}/events`}
                className="inline-flex min-h-[40px] items-center text-sm font-medium text-accent-text underline-offset-2 hover:underline"
              >
                {t('allEvents')}
              </Link>
            )}
          </div>

          {upcomingEvents.length === 0 ? (
            <Card className="p-6 text-center text-muted">
              {t('noUpcomingEvents')}
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {upcomingEvents.map((event) => (
                <EventCard key={event.id} event={event} />
              ))}
            </div>
          )}
        </section>

        {/*
          Community is a separate destination inside the artist experience
          rather than content embedded in the overview, so this card only
          points at it.
        */}
        <section aria-labelledby="community-heading">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2
              id="community-heading"
              className="text-xl font-bold sm:text-2xl"
            >
              {t('community')}
            </h2>
          </div>

          <Card className="p-5 sm:p-6">
            <p className="mb-4 text-muted">
              {tCommunity('aboutArtist', { artist: artist.name })}
            </p>

            <Link
              href={`/${locale}/artists/${artistSlug}/community`}
              data-testid="artist-community-link"
              className="inline-flex min-h-[44px] items-center rounded-lg border border-accent px-4 text-sm font-semibold text-accent-text transition-colors hover:bg-accent/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              {t('tabCommunity')}
            </Link>
          </Card>
        </section>

        {relatedArtists.length > 0 && (
          <section aria-labelledby="related-artists-heading">
            <h2
              id="related-artists-heading"
              className="mb-4 text-xl font-bold sm:text-2xl"
            >
              {t('relatedArtists')}
            </h2>

            {relatedLoading ? (
              <Card className="p-6 text-center text-muted">
                {t('loadingRelated')}
              </Card>
            ) : (
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                {relatedArtists.map((relatedArtist, index) => (
                  <Link
                    key={relatedArtist.slug ?? index}
                    href={`/${locale}/artists/${relatedArtist.slug}`}
                    className="block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  >
                    <Card hoverable className="p-4 text-center">
                      {relatedArtist.image && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={relatedArtist.image}
                          alt={relatedArtist.name}
                          loading="lazy"
                          className="mb-3 h-32 w-full rounded-lg object-cover"
                        />
                      )}
                      <p className="line-clamp-1 text-sm font-semibold">
                        {relatedArtist.name}
                      </p>
                    </Card>
                  </Link>
                ))}
              </div>
            )}
          </section>
        )}
      </div>

      {!signedIn && (
        <p className="sr-only">{t('followLoginRequired')}</p>
      )}
    </div>
  );
}
