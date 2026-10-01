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
import { useTranslations } from 'next-intl';

import {
  artistAPI,
  eventAPI,
  showLogAPI,
} from '../../../lib/api';

import { isAuthenticated } from '../../../lib/auth';
import { useAuthAction } from '../../../lib/use-auth-action';

import Button from '../../../../components/ui/Button';
import Card from '../../../../components/ui/Card';
import LoadingState from '../../../../components/LoadingState';

import { format } from 'date-fns';

interface ArtistSummary {
  songkick_id?: string;
  slug: string;
  name: string;
  url?: string;
  image?: string | null;
}

interface Venue {
  id?: string | null;
  slug?: string | null;
  name: string;
  city?: string | null;
  country?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

interface Festival {
  name?: string | null;
  edition?: string | null;
  url?: string | null;
  official_url?: string | null;
  artists?: ArtistSummary[];
  is_flagged_as_ended?: boolean;
}

interface Location {
  city?: string | null;
  country?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

interface Event {
  id: string;
  title: string;
  artist_slug?: string;
  artist_slugs?: string[];
  venue_slug?: string;
  venue?: Venue | null;
  starts_at: string;
  ends_at?: string | null;
  event_type?: string;
  ticket_url?: string | null;
  sold_out?: boolean;
  free?: boolean;
  festival?: Festival | null;
  location?: Location | null;
  going_count?: number;
  maybe_count?: number;
  went_count?: number;
  description?: string | null;
  image_url?: string | null;
}

type EventStatus = 'upcoming' | 'happening' | 'past';
type EventTab = 'information' | 'posts' | 'artists';

export default function EventDetailPage() {
  const router = useRouter();
  const params = useParams();
  const eventId = params.id as string;
  const locale = (params.locale as string) || 'en';
  const t = useTranslations('event');

  const runAuthAction = useAuthAction({ locale });
  const tArtist = useTranslations('artist');

  const [event, setEvent] = useState<Event | null>(null);
  const [showLog, setShowLog] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<EventTab>('information');
  const [loadingArtistSlug, setLoadingArtistSlug] = useState<string | null>(null);

  useEffect(() => {
    loadEvent();
    loadShowLog();
  }, [eventId]);

  async function loadEvent() {
    try {
      setLoading(true);
      const data = await eventAPI.getEvent(eventId);
      setEvent(data);
    } catch (error) {
      console.error('Failed loading event', error);
      setEvent(null);
    } finally {
      setLoading(false);
    }
  }

  async function loadShowLog() {
    if (!isAuthenticated()) {
      setShowLog(null);
      return;
    }

    try {
      const data = await showLogAPI.get(eventId);
      setShowLog(data);
    } catch (error) {
      setShowLog(null);
    }
  }

  function getEventStatus(currentEvent: Event): EventStatus {
    const now = Date.now();
    const startsAt = new Date(currentEvent.starts_at).getTime();
    const endsAt = currentEvent.ends_at
      ? new Date(currentEvent.ends_at).getTime()
      : null;

    const hasValidEnd =
      endsAt !== null &&
      Number.isFinite(endsAt) &&
      endsAt > startsAt;

    if (now < startsAt) {
      return 'upcoming';
    }

    if (hasValidEnd && now <= endsAt) {
      return 'happening';
    }

    if (!hasValidEnd) {
      return 'happening';
    }

    return 'past';
  }

  const eventStatus = event
    ? getEventStatus(event)
    : 'upcoming';

  const isEventPast = eventStatus === 'past';
  const isEventHappening = eventStatus === 'happening';
  const isFestival = event?.event_type === 'FestivalInstance';

  const artistSlugs = useMemo(() => {
    if (!event) {
      return [];
    }

    if (event.artist_slugs?.length) {
      return event.artist_slugs;
    }

    return event.artist_slug
      ? [event.artist_slug]
      : [];
  }, [event]);

  const lineup = useMemo(() => {
    const artists = event?.festival?.artists ?? [];

    return [...artists].sort((a, b) =>
      a.name.localeCompare(b.name, 'pt-BR')
    );
  }, [event]);

  const linkedArtists = useMemo(() => {
    if (!event) {
      return [];
    }

    if (lineup.length === 0) {
      return artistSlugs.map((slug) => ({
        slug,
        name: slug
          .split('-')
          .map((part) =>
            part.charAt(0).toUpperCase() + part.slice(1)
          )
          .join(' '),
      }));
    }

    return artistSlugs.map((slug) => {
      const lineupArtist = lineup.find(
        (artist) => artist.slug === slug
      );

      return {
        slug,
        name: lineupArtist?.name || slug
          .split('-')
          .map((part) =>
            part.charAt(0).toUpperCase() + part.slice(1)
          )
          .join(' '),
      };
    });
  }, [artistSlugs, event, lineup]);

  const formattedDate = event
    ? format(new Date(event.starts_at), 'MMMM d, yyyy')
    : '';

  const formattedTime = event
    ? format(new Date(event.starts_at), 'h:mm a')
    : '';

  const eventTypeLabel = isFestival
    ? 'Festival'
    : 'Concert';

  const statusLabel =
    eventStatus === 'past'
      ? 'Past'
      : isEventHappening
        ? 'Happening now'
        : 'Upcoming';

  const statusClasses =
    eventStatus === 'past'
      ? 'border-gray-500/30 bg-gray-500/10 text-gray-400'
      : isEventHappening
        ? 'border-accent/40 bg-accent/10 text-accent'
        : 'border-accent/30 bg-accent/5 text-accent';

  const festivalName = event?.festival?.name || event?.title;

  const displayTitle = isFestival && linkedArtists.length > 0
    ? `${linkedArtists[0].name} @ ${festivalName}`
    : event?.title || '';

  // Marking attendance changes user-specific data. Signed-out visitors are
  // sent to the localized login (preserving locale and current page) instead
  // of firing a protected request.
  function requireLogin(callback: () => void) {
    runAuthAction(callback);
  }

  function handleTabChange(tab: EventTab) {
    if (tab === 'posts' && !isEventPast) {
      return;
    }

    if (tab === 'artists' && (!isFestival || !isEventPast)) {
      return;
    }

    setActiveTab(tab);
  }

  async function handleShowLog(
    status: 'going' | 'maybe' | 'went'
  ) {
    if (!event) {
      return;
    }

    if (isEventPast && status !== 'went') {
      return;
    }

    try {
      setSubmitting(true);

      if (showLog?.status === status) {
        await showLogAPI.delete(eventId);
        setShowLog(null);
        await loadEvent();
        return;
      }

      await showLogAPI.create({
        event_id: eventId,
        status,
      });

      await loadShowLog();
      await loadEvent();
    } catch (error) {
      console.error('Failed updating attendance', error);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleFestivalArtistClick(artist: ArtistSummary) {
    if (!artist.slug) {
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
        // Artist is probably not imported under the Songkick slug yet.
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
        <LoadingState message="Loading event..." />
      </div>
    );
  }

  if (!event) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="text-center">
          <p className="text-gray-400 mb-4">{t('notFound')}</p>

          <Link
            href="/events"
            className="text-accent hover:text-accent/80"
          >
            ← Back to events
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <main className="max-w-6xl mx-auto px-4 py-8">
        <Link
          href="/events"
          className="inline-flex items-center text-sm text-accent hover:text-accent/80 transition"
        >
          ← Back to events
        </Link>

        <section className="mt-6 relative overflow-hidden rounded-2xl border border-border bg-card-bg">
          {event.image_url && (
            <div className="absolute inset-0 opacity-15">
              <img
                src={event.image_url}
                alt=""
                className="w-full h-full object-cover blur-sm"
              />
            </div>
          )}

          <div className="relative p-6 md:p-8">
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <span className="inline-flex items-center rounded-full border border-border bg-background/50 px-3 py-1 text-xs font-medium">
                {eventTypeLabel}
              </span>

              <span
                className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium ${statusClasses}`}
              >
                {statusLabel}
              </span>
            </div>

            <h1 className="max-w-4xl text-3xl md:text-5xl font-bold tracking-tight">
              {displayTitle}
            </h1>

            {isFestival && linkedArtists.length > 0 && (
              <div className="mt-5 flex flex-wrap items-center gap-2 text-sm">
                <span className="text-gray-500">{t('artist')}</span>

                {linkedArtists.map((artist, index) => (
                  <span key={artist.slug}>
                    {index > 0 && (
                      <span className="text-gray-600 mx-1">
                        ·
                      </span>
                    )}

                    <Link
                      href={`/artists/${artist.slug}`}
                      className="text-accent hover:text-accent/80 transition"
                    >
                      {artist.name}
                    </Link>
                  </span>
                ))}
              </div>
            )}

            <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4 max-w-3xl">
              <div>
                <p className="text-xs uppercase tracking-wide text-gray-500 mb-1">{t('date')}</p>

                <p className="text-gray-200">
                  {formattedDate}
                </p>

                {!isFestival && (
                  <p className="text-sm text-gray-400 mt-1">
                    {formattedTime}
                  </p>
                )}
              </div>

              <div>
                <p className="text-xs uppercase tracking-wide text-gray-500 mb-1">{t('venue')}</p>

                <p className="text-gray-200">
                  {event.venue?.name ||
                    event.venue_slug ||
                    'Location unavailable'}
                </p>

                {(event.location?.city || event.venue?.city) && (
                  <p className="text-sm text-gray-400 mt-1">
                    {event.location?.city || event.venue?.city}
                    {(event.location?.country || event.venue?.country) && (
                      <>
                        {' • '}
                        {event.location?.country || event.venue?.country}
                      </>
                    )}
                  </p>
                )}
              </div>
            </div>

            {isFestival && (
              <div className="mt-6">
                <Link
                  href={`/festivals/${event.id}`}
                  className="inline-flex items-center text-sm text-accent hover:text-accent/80 transition"
                >
                  View festival page →
                </Link>
              </div>
            )}
          </div>
        </section>

        <div className="mt-8 border-b border-border">
          <div className="flex items-end gap-7 overflow-x-auto">
            <button
              type="button"
              onClick={() => handleTabChange('information')}
              className={`pb-3 text-sm font-medium whitespace-nowrap border-b-2 transition ${
                activeTab === 'information'
                  ? 'border-accent text-foreground'
                  : 'border-transparent text-gray-500 hover:text-gray-300'
              }`}
            >{t('information')}</button>

            <button
              type="button"
              onClick={() => handleTabChange('posts')}
              disabled={!isEventPast}
              className={`pb-3 text-sm font-medium whitespace-nowrap border-b-2 transition ${
                activeTab === 'posts'
                  ? 'border-accent text-foreground'
                  : isEventPast
                    ? 'border-transparent text-gray-500 hover:text-gray-300'
                    : 'border-transparent text-gray-700 cursor-not-allowed'
              }`}
            >{t('posts')}</button>

            {isFestival && isEventPast && (
              <button
                type="button"
                onClick={() => handleTabChange('artists')}
                className={`pb-3 text-sm font-medium whitespace-nowrap border-b-2 transition ${
                  activeTab === 'artists'
                    ? 'border-accent text-foreground'
                    : 'border-transparent text-gray-500 hover:text-gray-300'
                }`}
              >{t('artists')}</button>
            )}
          </div>
        </div>

        {activeTab === 'information' && (
          <div className="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-2 space-y-8">
              <Card className="p-6">
                <h2 className="text-xl font-bold mb-6">{t('eventInformation')}</h2>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <p className="text-xs uppercase tracking-wide text-gray-500 mb-1">{t('date')}</p>

                    <p className="text-gray-200">
                      {formattedDate}
                    </p>
                  </div>

                  {!isFestival && (
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500 mb-1">{t('startTime')}</p>

                      <p className="text-gray-200">
                        {formattedTime}
                      </p>
                    </div>
                  )}

                  <div>
                    <p className="text-xs uppercase tracking-wide text-gray-500 mb-1">{t('type')}</p>

                    <p className="text-gray-200">
                      {eventTypeLabel}
                    </p>
                  </div>

                  <div>
                    <p className="text-xs uppercase tracking-wide text-gray-500 mb-1">{t('status')}</p>

                    <p className="text-gray-200">
                      {statusLabel}
                    </p>
                  </div>
                </div>

                {event.description && (
                  <div className="mt-8 border-t border-border pt-6">
                    <p className="text-xs uppercase tracking-wide text-gray-500 mb-2">{t('about')}</p>

                    <p className="text-gray-400 leading-relaxed">
                      {event.description}
                    </p>
                  </div>
                )}
              </Card>

              {isFestival && event.festival && (
                <Card className="p-6">
                  <p className="text-xs uppercase tracking-wide text-accent mb-2">{t('festival')}</p>

                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <div>
                      <h2 className="text-xl font-bold">
                        {event.festival.name || event.title}
                      </h2>

                      <p className="text-sm text-gray-500 mt-1">{t('lineupHint')}</p>
                    </div>

                    <Link
                      href={`/festivals/${event.id}`}
                      className="text-sm text-accent hover:text-accent/80 transition shrink-0"
                    >
                      Explore festival →
                    </Link>
                  </div>
                </Card>
              )}

              <Card className="p-6">
                <h2 className="text-xl font-bold mb-5">{t('location')}</h2>

                <div className="space-y-2">
                  <p className="text-lg font-semibold">
                    {event.venue?.name ||
                      event.venue_slug ||
                      'Venue unavailable'}
                  </p>

                  {(event.location?.city ||
                    event.venue?.city ||
                    event.location?.country ||
                    event.venue?.country) && (
                    <p className="text-gray-400">
                      {event.location?.city || event.venue?.city}
                      {(event.location?.country || event.venue?.country) && (
                        <>
                          {' • '}
                          {event.location?.country || event.venue?.country}
                        </>
                      )}
                    </p>
                  )}

                  {event.location?.latitude !== null &&
                    event.location?.latitude !== undefined &&
                    event.location?.longitude !== null &&
                    event.location?.longitude !== undefined && (
                      <a
                        href={`https://www.google.com/maps?q=${event.location.latitude},${event.location.longitude}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex mt-3 text-sm text-accent hover:text-accent/80 transition"
                      >
                        Open in maps ↗
                      </a>
                    )}
                </div>
              </Card>
            </div>

            <aside>
              <Card className="p-6 space-y-6 lg:sticky lg:top-6">
                <div>
                  <h2 className="text-lg font-bold mb-4">{t('yourAttendance')}</h2>

                  <div className="space-y-3">
                    {!isEventPast && (
                      <>
                        <Button
                          disabled={submitting}
                          onClick={() =>
                            requireLogin(() =>
                              handleShowLog('going')
                            )
                          }
                          variant={
                            showLog?.status === 'going'
                              ? 'neon'
                              : 'outlineGradient'
                          }
                          className="w-full"
                        >
                          ✓ I'm going
                        </Button>

                        <Button
                          disabled={submitting}
                          onClick={() =>
                            requireLogin(() =>
                              handleShowLog('maybe')
                            )
                          }
                          variant={
                            showLog?.status === 'maybe'
                              ? 'neon'
                              : 'outlineGradient'
                          }
                          className="w-full"
                        >
                          ? Maybe
                        </Button>
                      </>
                    )}

                    {isEventPast && (
                      <Button
                        disabled={submitting}
                        onClick={() =>
                          requireLogin(() =>
                            handleShowLog('went')
                          )
                        }
                        variant={
                          showLog?.status === 'went'
                            ? 'neon'
                            : 'outlineGradient'
                        }
                        className="w-full"
                      >
                        ✓ I Went
                      </Button>
                    )}
                  </div>
                </div>

                {!isEventPast && (
                  <div className="border-t border-border pt-6">
                    <h2 className="text-lg font-bold mb-3">{t('tickets')}</h2>

                    {event.free ? (
                      <p className="text-accent">{t('freeEvent')}</p>
                    ) : event.sold_out ? (
                      <p className="text-gray-500">{t('soldOut')}</p>
                    ) : event.ticket_url ? (
                      <a
                        href={event.ticket_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block"
                      >
                        <Button
                          variant="primary"
                          className="w-full"
                        >{t('getTickets')}</Button>
                      </a>
                    ) : (
                      <p className="text-gray-500">{t('ticketUnavailable')}</p>
                    )}
                  </div>
                )}

                <div className="border-t border-border pt-6">
                  <div className="grid grid-cols-3 text-center gap-2">
                    <div>
                      <strong className="text-lg">
                        {event.going_count ?? 0}
                      </strong>
                      <p className="text-xs text-gray-500">{t('going')}</p>
                    </div>

                    <div>
                      <strong className="text-lg">
                        {event.maybe_count ?? 0}
                      </strong>
                      <p className="text-xs text-gray-500">{t('maybe')}</p>
                    </div>

                    <div>
                      <strong className="text-lg">
                        {event.went_count ?? 0}
                      </strong>
                      <p className="text-xs text-gray-500">{t('went')}</p>
                    </div>
                  </div>
                </div>
              </Card>
            </aside>
          </div>
        )}

        {activeTab === 'posts' && isEventPast && (
          <section className="mt-8">
            <Card className="p-8">
              <div className="max-w-xl mx-auto text-center py-8">
                <div className="text-4xl mb-4">
                  ✦
                </div>

                <h2 className="text-xl font-bold mb-2">{t('postsAboutEvent')}</h2>

                <p className="text-gray-500 leading-relaxed">
                  This is where the GigCrowd community will share photos,
                  stories and moments from this event.
                </p>
              </div>
            </Card>
          </section>
        )}

        {activeTab === 'artists' && isFestival && isEventPast && (
          <section className="mt-8">
            <Card className="p-6 md:p-8">
              <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-wide text-accent mb-2">{t('festivalLineup')}</p>

                  <h2 className="text-2xl font-bold">
                    {lineup.length} artists
                  </h2>
                </div>

                <Link
                  href={`/festivals/${event.id}`}
                  className="text-sm text-accent hover:text-accent/80 transition"
                >
                  Open festival page →
                </Link>
              </div>

              {lineup.length === 0 ? (
                <p className="py-12 text-center text-gray-500">{t('lineupUnavailable')}</p>
              ) : (
                <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {lineup.map((artist) => {
                    const isLoading = loadingArtistSlug === artist.slug;

                    return (
                      <button
                        key={artist.songkick_id || artist.slug}
                        type="button"
                        onClick={() => handleFestivalArtistClick(artist)}
                        disabled={isLoading}
                        className="flex items-center gap-3 rounded-xl border border-border bg-background/20 p-4 text-left hover:border-accent hover:bg-card-hover transition disabled:opacity-60 disabled:cursor-wait"
                      >
                        {artist.image ? (
                          <img
                            src={artist.image}
                            alt={artist.name}
                            className="h-12 w-12 rounded-full object-cover shrink-0"
                          />
                        ) : (
                          <div className="h-12 w-12 rounded-full bg-card-hover flex items-center justify-center text-lg shrink-0">
                            ♪
                          </div>
                        )}

                        <span className="min-w-0 flex-1">
                          <span className="block font-medium truncate">
                            {artist.name}
                          </span>

                          <span className="block text-xs text-gray-500 mt-1">
                            {isLoading ? 'Opening artist...' : 'Open artist'}
                          </span>
                        </span>

                        <span className="text-accent shrink-0">
                          →
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </Card>
          </section>
        )}
      </main>
    </div>
  );
}
