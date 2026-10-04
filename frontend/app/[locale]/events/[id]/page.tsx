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
import {
  resolveLocale,
  formatEventDateRange,
  formatEventTime,
  byNameInLocale,
  formatEventSchedule,
  isHappeningNow,
  isPastEvent,
} from '../../../lib/dates';

import Button from '../../../../components/ui/Button';
import Card from '../../../../components/ui/Card';
import LoadingState from '../../../../components/LoadingState';
import ReviewCard from '../../../../components/ReviewCard';
import ReviewDialog from '../../../../components/ReviewDialog';
import type {
  ReviewPayload,
  ShowLog,
} from '../../../../app/types/review';
import type { ProfileReview } from '../../../../app/types/profile';

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

interface LineupArtist {
  name: string;
  /**
   * The Songkick artist id, taken from the artist's own URL on the source
   * page. Its absence means the source listed a performer without one, so the
   * entry is still shown but cannot be matched to an artist.
   */
  songkick_id?: string | null;
  slug?: string | null;
  url?: string | null;
  image?: string | null;
  genres?: string[];
  order?: number;
}

interface Event {
  id: string;
  title: string;
  artist_slug?: string;
  artist_slugs?: string[];
  venue_slug?: string;
  venue?: Venue | null;
  starts_at?: string | null;
  ends_at?: string | null;
  /**
   * Resolved by the backend from `starts_at`/`ends_at`, which are optional on
   * imported events. The client never re-derives it from a date that may be
   * missing.
   */
  is_past?: boolean;
  event_type?: string;
  ticket_url?: string | null;
  sold_out?: boolean;
  free?: boolean;
  festival?: Festival | null;
  /**
   * How the dates above were resolved. `unavailable` is a real state the page
   * has to render honestly; it is not an invitation to invent a date.
   */
  date_status?: string | null;
  lineup?: LineupArtist[];
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
  const locale = resolveLocale(params.locale as string);
  const t = useTranslations('event');

  const runAuthAction = useAuthAction({ locale });
  const tArtist = useTranslations('artist');

  const [event, setEvent] = useState<Event | null>(null);
  const [showLog, setShowLog] = useState<ShowLog | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<EventTab>('information');
  const [loadingArtistSlug, setLoadingArtistSlug] = useState<string | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [attendanceError, setAttendanceError] = useState<string | null>(null);

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

  /*
    `isPastEvent` prefers the backend's `is_past` and only falls back to the
    later of the two dates. The previous local rule returned "happening" for any
    event without a usable `ends_at`, which left a finished concert reading as
    ongoing forever and put "I went" permanently out of reach.
  */
  const isEventPast = isPastEvent(event);
  const isEventHappening = isHappeningNow(event);
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

  /**
   * The lineup as the event's own source announced it.
   *
   * This used to be read from `event.festival.artists`, which the importer
   * never populated, so a festival with thirty artists on the bill rendered an
   * empty list. The event carries its own lineup now, with each performer's
   * Songkick id, so the same data the festival page shows is available here.
   *
   * Entries are shown as names rather than links: this endpoint does not resolve
   * them to GigCrowd artists, and a link to a page that may not exist - or an
   * artist created on click to make one - would both be worse than the name.
   * The festival page resolves and links them.
   */
  const lineup = useMemo(() => {
    return byNameInLocale(
      event?.lineup ?? [],
      locale,
    );
  }, [event, locale]);

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

  // Imported events carry a date often enough that every one of these has to
  // cope with it being absent, and the wording lives in the message catalog.
  const formattedDate = event
    ? formatEventSchedule(event, locale, t('dateUnavailable'))
    : '';

  const formattedTime = event?.starts_at
    ? formatEventTime(event.starts_at, locale)
    : null;

  const eventTypeLabel = isFestival
    ? t('festival')
    : t('concert');

  const statusLabel =
    isEventPast
      ? t('past')
      : isEventHappening
        ? t('happeningNow')
        : t('upcoming');

  const statusClasses =
    isEventPast
      ? 'border-border bg-card-hover text-muted'
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

    /*
      Attendance is a record of having been there, so it cannot be silently
      undone with one more tap: pressing "I went" again is how a review is
      written. Going and maybe stay one-tap toggles.
    */
    if (status === 'went' && showLog?.status === 'went') {
      setReviewOpen(true);
      return;
    }

    try {
      setSubmitting(true);
      setAttendanceError(null);

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

      if (status === 'went') {
        // Attendance is recorded; the review is the natural next step, so the
        // dialog opens where the reader already is.
        setReviewOpen(true);
      }
    } catch (error) {
      console.error('Failed updating attendance', error);
      setAttendanceError(t('attendanceFailed'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReviewSave(payload: ReviewPayload) {
    const saved = await showLogAPI.saveReview(eventId, payload);

    setShowLog(saved);
    setReviewOpen(false);
    await loadEvent();
  }

  async function handleReviewDelete() {
    const cleared = await showLogAPI.deleteReview(eventId);

    setShowLog(cleared);
    await loadEvent();
  }

  /*
    The signed-in user's own review, rendered through the same card the profile
    uses. Reviews other people wrote are shown on the post tab instead, so a
    reader and a bystander never see the same event page with different rules.
  */
  const ownReview: ProfileReview | null =
    showLog?.rating && isEventPast
      ? {
          event_id: eventId,
          title: event?.title ?? '',
          starts_at: event?.starts_at ?? null,
          ends_at: event?.ends_at ?? null,
          event_type: event?.event_type ?? 'Concert',
          artist_slugs: artistSlugs,
          artist_names: linkedArtists.map((artist) => artist.name),
          rating: showLog.rating,
          review: showLog.review ?? null,
          photo_url: showLog.photo_url ?? null,
          reviewed_at: showLog.reviewed_at ?? null,
        }
      : null;

  async function handleFestivalArtistClick(artist: ArtistSummary) {
    if (!artist.slug) {
      return;
    }

    try {
      setLoadingArtistSlug(artist.slug);

      try {
        const existingArtist = await artistAPI.getArtist(artist.slug);

        if (existingArtist?.slug) {
          router.push(`/${locale}/artists/${existingArtist.slug}`);
          return;
        }
      } catch (error) {
        // Artist is probably not imported under the Songkick slug yet.
      }

      if (!artist.songkick_id) {
        router.push(`/${locale}/artists/${artist.slug}`);
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
        router.push(`/${locale}/artists/${importedArtist.slug}`);
        return;
      }

      router.push(`/${locale}/artists/${artist.slug}`);
    } catch (error) {
      console.error('Failed opening festival artist', error);
    } finally {
      setLoadingArtistSlug(null);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingState message={t('loading')} />
      </div>
    );
  }

  if (!event) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="text-center">
          <p className="text-muted mb-4">{t('notFound')}</p>

          <Link
            href={`/${locale}/events`}
            className="text-accent hover:text-accent/80"
          >
            {t('backToEvents')}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <main className="max-w-6xl mx-auto px-4 py-8">
        <Link
          href={`/${locale}/events`}
          className="inline-flex items-center text-sm text-accent hover:text-accent/80 transition"
        >
          {t('backToEvents')}
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
                <span className="text-muted-subtle">{t('artist')}</span>

                {linkedArtists.map((artist, index) => (
                  <span key={artist.slug}>
                    {index > 0 && (
                      <span className="text-disabled mx-1">
                        ·
                      </span>
                    )}

                    <Link
                      href={`/${locale}/artists/${artist.slug}`}
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
                <p className="text-xs uppercase tracking-wide text-muted-subtle mb-1">{t('date')}</p>

                <p className="text-foreground">
                  {formattedDate}
                </p>

                {!isFestival && formattedTime && (
                  <p className="text-sm text-muted mt-1">
                    {formattedTime}
                  </p>
                )}
              </div>

              <div>
                <p className="text-xs uppercase tracking-wide text-muted-subtle mb-1">{t('venue')}</p>

                <p className="text-foreground">
                  {event.venue?.name ||
                    event.venue_slug ||
                    t('locationUnavailable')}
                </p>

                {(event.location?.city || event.venue?.city) && (
                  <p className="text-sm text-muted mt-1">
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
                  href={`/${locale}/festivals/${event.id}`}
                  className="inline-flex items-center text-sm text-accent hover:text-accent/80 transition"
                >
                  {t('viewFestivalPage')}
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
                  : 'border-transparent text-muted-subtle hover:text-foreground'
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
                    ? 'border-transparent text-muted-subtle hover:text-foreground'
                    : 'border-transparent text-disabled cursor-not-allowed'
              }`}
            >{t('posts')}</button>

            {isFestival && isEventPast && (
              <button
                type="button"
                onClick={() => handleTabChange('artists')}
                className={`pb-3 text-sm font-medium whitespace-nowrap border-b-2 transition ${
                  activeTab === 'artists'
                    ? 'border-accent text-foreground'
                    : 'border-transparent text-muted-subtle hover:text-foreground'
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
                    <p className="text-xs uppercase tracking-wide text-muted-subtle mb-1">{t('date')}</p>

                    <p className="text-foreground">
                      {formattedDate}
                    </p>
                  </div>

                  {!isFestival && formattedTime && (
                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-subtle mb-1">{t('startTime')}</p>

                      <p className="text-foreground">
                        {formattedTime}
                      </p>
                    </div>
                  )}

                  <div>
                    <p className="text-xs uppercase tracking-wide text-muted-subtle mb-1">{t('type')}</p>

                    <p className="text-foreground">
                      {eventTypeLabel}
                    </p>
                  </div>

                  <div>
                    <p className="text-xs uppercase tracking-wide text-muted-subtle mb-1">{t('status')}</p>

                    <p className="text-foreground">
                      {statusLabel}
                    </p>
                  </div>
                </div>

                {event.description && (
                  <div className="mt-8 border-t border-border pt-6">
                    <p className="text-xs uppercase tracking-wide text-muted-subtle mb-2">{t('about')}</p>

                    <p className="text-muted leading-relaxed">
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

                      <p className="text-sm text-muted-subtle mt-1">{t('lineupHint')}</p>
                    </div>

                    <Link
                      href={`/${locale}/festivals/${event.id}`}
                      className="text-sm text-accent hover:text-accent/80 transition shrink-0"
                    >
                      {t('exploreFestival')}
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
                      t('venueUnavailable')}
                  </p>

                  {(event.location?.city ||
                    event.venue?.city ||
                    event.location?.country ||
                    event.venue?.country) && (
                    <p className="text-muted">
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
                        {t('openInMaps')}
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
                          {t('markGoing')}
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
                          {t('markMaybe')}
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
                        data-testid="event-mark-went"
                      >
                        {showLog?.status === 'went'
                          ? t('editReview')
                          : t('markWent')}
                      </Button>
                    )}

                    {attendanceError && (
                      <p
                        role="alert"
                        className="text-sm text-accent-text"
                        data-testid="attendance-error"
                      >
                        {attendanceError}
                      </p>
                    )}
                  </div>

                  {ownReview && !reviewOpen && (
                    <div className="border-t border-border pt-6">
                      <h2 className="text-lg font-bold mb-3">
                        {t('yourReviewHeading')}
                      </h2>

                      <ReviewCard
                        review={ownReview}
                        locale={locale}
                      />

                      <Button
                        variant="outlineGradient"
                        className="mt-4 w-full"
                        onClick={() => setReviewOpen(true)}
                        data-testid="event-edit-review"
                      >
                        {t('editReview')}
                      </Button>
                    </div>
                  )}
                </div>

                {!isEventPast && (
                  <div className="border-t border-border pt-6">
                    <h2 className="text-lg font-bold mb-3">{t('tickets')}</h2>

                    {event.free ? (
                      <p className="text-accent">{t('freeEvent')}</p>
                    ) : event.sold_out ? (
                      <p className="text-muted-subtle">{t('soldOut')}</p>
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
                      <p className="text-muted-subtle">{t('ticketUnavailable')}</p>
                    )}
                  </div>
                )}

                <div className="border-t border-border pt-6">
                  <div className="grid grid-cols-3 text-center gap-2">
                    <div>
                      <strong className="text-lg">
                        {event.going_count ?? 0}
                      </strong>
                      <p className="text-xs text-muted-subtle">{t('going')}</p>
                    </div>

                    <div>
                      <strong className="text-lg">
                        {event.maybe_count ?? 0}
                      </strong>
                      <p className="text-xs text-muted-subtle">{t('maybe')}</p>
                    </div>

                    <div>
                      <strong className="text-lg">
                        {event.went_count ?? 0}
                      </strong>
                      <p className="text-xs text-muted-subtle">{t('went')}</p>
                    </div>
                  </div>
                </div>
              </Card>
            </aside>
          </div>
        )}

        <ReviewDialog
          open={reviewOpen}
          eventTitle={displayTitle}
          showLog={showLog}
          onClose={() => setReviewOpen(false)}
          onSave={handleReviewSave}
          onDelete={handleReviewDelete}
        />

        {activeTab === 'posts' && isEventPast && (
          <section className="mt-8">
            <Card className="p-8">
              <div className="max-w-xl mx-auto text-center py-8">
                <div className="text-4xl mb-4">
                  ✦
                </div>

                <h2 className="text-xl font-bold mb-2">{t('postsAboutEvent')}</h2>

                <p className="text-muted-subtle leading-relaxed">
                  {t('postsAboutEventDescription')}
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
                    {t('artistsCount', {
                      count: lineup.length,
                    })}
                  </h2>
                </div>

                <Link
                  href={`/${locale}/festivals/${event.id}`}
                  className="text-sm text-accent hover:text-accent/80 transition"
                >
                  {t('openFestivalPage')}
                </Link>
              </div>

              {lineup.length === 0 ? (
                <p className="py-12 text-center text-muted-subtle">{t('lineupUnavailable')}</p>
              ) : (
                <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {lineup.map((artist) => (
                    <div
                      key={
                        artist.songkick_id ||
                        artist.name
                      }
                      data-testid="event-lineup-entry"
                      className="flex items-center gap-3 rounded-xl border border-border bg-background/20 p-4 text-left"
                    >
                      {artist.image ? (
                        <img
                          src={artist.image}
                          alt=""
                          loading="lazy"
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

                        <span className="block text-xs text-muted-subtle mt-1">
                          {t('artistNotImported')}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </section>
        )}
      </main>
    </div>
  );
}
