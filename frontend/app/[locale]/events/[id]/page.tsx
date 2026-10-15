'use client';

import {
  useEffect,
  useMemo,
  useRef,
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
import {
  eventDisplayTitle,
  festivalDisplayName,
} from '../../../lib/festivalTitle';
import { festivalSeriesId } from '../../../lib/festivalIdentity';
import { createRequestGuard } from '../../../lib/requestGuard';
import { createArtistOpener } from '../../../lib/artistSync';

import Button from '../../../../components/ui/Button';
import Card from '../../../../components/ui/Card';
import ArtistSyncLoading from '../../../../components/ui/ArtistSyncLoading';
import LoadingState from '../../../../components/LoadingState';
import ReviewCard from '../../../../components/ReviewCard';
import ReviewDialog from '../../../../components/ReviewDialog';
import LineupPerformerCard, {
  type LineupPerformer,
} from '../../../../components/festival/LineupPerformerCard';
import { logCarriesReview } from '../../../../app/lib/reviewValidation';
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
  series_id?: string | null;
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

/**
 * The Songkick artist id, taken from the artist's own URL on the source page.
 * Its absence means the source listed a performer without one, so the entry is
 * still shown but cannot be matched to an artist.
 */
type LineupArtist = LineupPerformer & { order?: number };

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
  /**
   * When the source was last actually read for a date. Distinguishes
   * "checked, and there is no date" from "a listing simply lacked one".
   */
  date_source_checked_at?: string | null;
  /**
   * The provider's scheduling state - schema.org `eventStatus`, stored as the
   * provider wrote it, so typically `https://schema.org/EventCancelled`.
   * Optional: most events state nothing, and absent means "no word from the
   * source", never "confirmed on".
   */
  event_status?: string | null;
  lineup?: LineupArtist[];
  location?: Location | null;
  going_count?: number;
  maybe_count?: number;
  went_count?: number;
  description?: string | null;
  image_url?: string | null;
  /**
   * Where the record came from. The address itself is load-bearing: it is
   * one of the places a festival series id is stated, and thus one of the
   * conditions under which a festival page for this event exists.
   */
  source?: {
    url?: string | null;
  } | null;
}

type EventStatus = 'upcoming' | 'happening' | 'past';
type EventTab = 'information' | 'posts' | 'artists';

/**
 * The two scheduling words a reader has to act on, or `null` for everything
 * else.
 *
 * The stored value is schema.org's own spelling, usually as a full URL
 * (`https://schema.org/EventCancelled`), so the last segment is what is
 * compared, case-insensitively - the provider's casing is not ours to rely
 * on. "Scheduled" resolves to null on purpose: a badge saying so on every
 * ordinary show is noise, and a state this function does not recognise stays
 * unlabelled rather than being guessed at.
 */
function resolveSchedulingState(
  value?: string | null,
): 'cancelled' | 'postponed' | null {
  const word =
    (value ?? '').split('/').pop()?.toLowerCase() ?? '';

  if (word === 'eventcancelled') {
    return 'cancelled';
  }

  if (word === 'eventpostponed') {
    return 'postponed';
  }

  return null;
}

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
  /*
    Pressing a lineup name that has no page here yet starts the on-demand
    import. These two states are the reader's view of that one operation:
    what is running, and - when it failed - who it was about, so a retry
    can repeat the very same request rather than ask to be pressed again.
  */
  const [openingArtist, setOpeningArtist] = useState<{
    phase: 'searching' | 'importing';
    performer: LineupArtist;
  } | null>(null);
  const [openFailure, setOpenFailure] = useState<{
    reason: 'failed' | 'unidentifiable';
    performer: LineupArtist;
  } | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [attendanceError, setAttendanceError] = useState<string | null>(null);

  /*
    Each loader owns a guard: only the most recently started request may
    write its answer, and the id check in front of every claim makes a
    request started for a previous page refuse to even compete - otherwise
    its late claim would outrank the current page's own load.
  */
  const eventRequest = useRef(createRequestGuard()).current;
  const showLogRequest = useRef(createRequestGuard()).current;
  const pageEventId = useRef(eventId);

  /*
    The page changes identity with its id while staying mounted. When that
    happens the previous event - and its attendance, the actions pending on
    it - are dropped during render itself, so no frame of the new URL can
    show the old event, and no answer that arrives later is ever applied to
    state that already belongs to someone else's show.
  */
  const [renderedEventId, setRenderedEventId] = useState(eventId);
  if (renderedEventId !== eventId) {
    setRenderedEventId(eventId);
    // The guards learn the new identity in the same pass, so a request that
    // resumes before the effects run already sees the page it must not touch.
    pageEventId.current = eventId;
    setEvent(null);
    setShowLog(null);
    setLoading(true);
    setSubmitting(false);
    setAttendanceError(null);
  }

  useEffect(() => {
    loadEvent();
    loadShowLog();
  }, [eventId]);

  async function loadEvent() {
    const target = eventId;
    if (pageEventId.current !== target) return;
    const request = eventRequest.next();
    const stillMine = () =>
      eventRequest.isCurrent(request) && pageEventId.current === target;
    try {
      setLoading(true);
      const data = await eventAPI.getEvent(target);
      if (!stillMine()) return;
      setEvent(data);
    } catch (error) {
      if (!stillMine()) return;
      console.error('Failed loading event', error);
      setEvent(null);
    } finally {
      if (stillMine()) setLoading(false);
    }
  }

  async function loadShowLog() {
    const target = eventId;
    if (pageEventId.current !== target) return;
    const request = showLogRequest.next();
    const stillMine = () =>
      showLogRequest.isCurrent(request) && pageEventId.current === target;
    if (!isAuthenticated()) {
      if (stillMine()) setShowLog(null);
      return;
    }

    try {
      const data = await showLogAPI.get(target);
      if (!stillMine()) return;
      setShowLog(data);
    } catch (error) {
      if (stillMine()) setShowLog(null);
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
  /*
    `FestivalInstance` is the canonical type, but rows written before the
    canonicalisation carry lowercase `festival`, so the check is a case-
    insensitive match on the substring the backend's `_is_festival_event`
    also accepts. Both spellings must render the same page.
  */
  const isFestival = (event?.event_type ?? '')
    .toLowerCase()
    .includes('festival');

  // A cancelled or postponed show says so beside its status badge; an event
  // whose source stated no scheduling word simply carries no badge.
  const schedulingState = resolveSchedulingState(
    event?.event_status,
  );

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
   * Each entry carries the GigCrowd page it resolved to, so a performer this
   * catalogue knows is a link - and one this catalogue does not know is a
   * name that becomes an on-demand import when pressed. Resolution is the
   * backend's, by Songkick id; this page never matches a name to a slug.
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

  /*
    The festival's own name when the importer recorded one; the event title
    is a fallback only, and only after the artist prefix is stripped. The
    header title then adds the artist's name just once - a name that already
    contains the artist, or already reads as a complete "Festival @ Venue"
    descriptor, is shown as it is. The shared rules live in
    `lib/festivalTitle`, so the festival card further down this page and any
    future caller cannot drift from what the header shows.
  */
  const linkedArtistName = linkedArtists[0]?.name;

  const displayTitle = isFestival
    ? eventDisplayTitle({
        festivalName: event?.festival?.name,
        title: event?.title,
        artistName: linkedArtistName,
      })
    : event?.title || '';

  /*
    A festival page for this event exists only when its identity is
    confirmed - a Songkick series id stated by the stored block, by one of
    its URLs, or by the event's own address (the legacy rows written without
    a block). Where nothing states one, the backend answers 404 and every
    link down this page to it is withheld rather than presented as an
    association the data never made. The rule mirrors `festival_identity`
    server-side; `lib/festivalIdentity` keeps the two from drifting.
  */
  const festivalSeries = event ? festivalSeriesId(event) : null;

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
        // The action answered for the event that was on screen when it was
        // pressed; if the reader has already moved on, its result - and the
        // reloads it would trigger - belong to the previous page.
        if (pageEventId.current !== eventId) return;
        setShowLog(null);
        await loadEvent();
        return;
      }

      await showLogAPI.create({
        event_id: eventId,
        status,
      });

      if (pageEventId.current !== eventId) return;

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
    if (pageEventId.current !== eventId) return;

    setShowLog(saved);
    setReviewOpen(false);
    await loadEvent();
  }

  async function handleReviewDelete() {
    const cleared = await showLogAPI.deleteReview(eventId);
    if (pageEventId.current !== eventId) return;

    setShowLog(cleared);
    await loadEvent();
  }

  /*
    The signed-in user's own review, rendered through the same card the profile
    uses. Reviews other people wrote are shown on the post tab instead, so a
    reader and a bystander never see the same event page with different rules.
    The gate reads what the log carries - rating, words, or a legacy photo -
    rather than only the rating, so an opinion written without stars is still
    the person's review of the show.
  */
  const ownReview: ProfileReview | null =
    showLog && isEventPast && logCarriesReview(showLog)
      ? {
          event_id: eventId,
          title: event?.title ?? '',
          starts_at: event?.starts_at ?? null,
          ends_at: event?.ends_at ?? null,
          event_type: event?.event_type ?? 'Concert',
          artist_slugs: artistSlugs,
          artist_names: linkedArtists.map((artist) => artist.name),
          rating: showLog.rating ?? null,
          review: showLog.review ?? null,
          photo_url: showLog.photo_url ?? null,
          reviewed_at: showLog.reviewed_at ?? null,
        }
      : null;

  /*
    One operation per press: the opener deduplicates by Songkick id while a
    call is in flight, so a second click - or any re-render that calls this
    again - shares the running import instead of starting another one. The
    identity is the lineup's Songkick id; the entry's own `slug` field is
    Songkick's namespace and is deliberately never looked up here (that is
    what the dead handler this replaced used to do).
  */
  const artistOpener = useMemo(
    () =>
      createArtistOpener({
        getArtist: (slug) => artistAPI.getArtist(slug),
        importArtist: (songkickId, provider, data) =>
          artistAPI.importArtist(songkickId, provider, data),
        navigate: (slug) => router.push(`/${locale}/artists/${slug}`),
      }),
    [router, locale],
  );

  function handleLineupArtistOpen(performer: LineupArtist) {
    // One overlay, one operation: a press while the previous is still
    // running belongs to the artist already being opened.
    if (openingArtist) {
      return;
    }

    setOpenFailure(null);
    setOpeningArtist({ phase: 'searching', performer });

    artistOpener
      .open(
        {
          // The GigCrowd slug, when the entry resolved to one. This
          // control only renders for entries that did not, so it is null.
          slug: performer.artist_slug ?? null,
          songkickId: performer.songkick_id,
          name: performer.name,
          url: performer.url,
        },
        (phase) =>
          setOpeningArtist((current) =>
            current
              ? {
                  ...current,
                  phase:
                    phase === 'import' ? 'importing' : 'searching',
                }
              : current,
          ),
      )
      .then(() => setOpeningArtist(null))
      .catch((error) => {
        setOpeningArtist(null);
        setOpenFailure({
          reason:
            (error as { reason?: string })?.reason === 'unidentifiable'
              ? 'unidentifiable'
              : 'failed',
          performer,
        });
      });
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
      {/*
        Pressed a lineup name with no page here yet? This overlay is the whole
        time between the press and that artist's page - the lookup, and on a
        first open the gigography import behind it. It is intentional, themed
        and centred rather than a black gap, and a failure lands in the same
        panel with a retry instead of leaving the page silently stuck.
      */}
      {(openingArtist || openFailure) && (
        <div
          className="
            fixed
            inset-0
            z-50
            flex
            items-center
            justify-center
            bg-background/80
            backdrop-blur-sm
            px-4
          "
          data-testid="artist-open-overlay"
        >
          <div className="rounded-2xl border border-border bg-card-bg p-8 shadow-xl">
            <ArtistSyncLoading
              phase={openingArtist?.phase ?? 'searching'}
              artistName={
                (openingArtist ?? openFailure)?.performer.name
              }
              failure={openFailure?.reason ?? null}
              onRetry={
                openFailure
                  ? () => handleLineupArtistOpen(openFailure.performer)
                  : undefined
              }
              onClose={
                openFailure ? () => setOpenFailure(null) : undefined
              }
            />
          </div>
        </div>
      )}

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

              {schedulingState && (
                <span
                  className="inline-flex items-center rounded-full border border-accent/40 bg-accent/10 px-3 py-1 text-xs font-medium text-accent"
                  data-testid="event-scheduling-state"
                >
                  {schedulingState === 'cancelled'
                    ? t('eventCancelled')
                    : t('eventPostponed')}
                </span>
              )}
            </div>

            <h1 className="max-w-4xl text-3xl md:text-5xl font-bold tracking-tight">
              {displayTitle}
            </h1>

            {/*
              Every event, not only a festival. `artist_slugs` are GigCrowd
              slugs the importer wrote for an artist it already knows, so the
              link is a trusted identity rather than a guess about the title,
              and opening it runs the same `pending -> initializing ->
              initialized` path every other artist page does. The festival-only
              guard that used to live here hid the one relationship a normal
              show has.
            */}
            {linkedArtists.length > 0 && (
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

            {isFestival && festivalSeries && (
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
                        {festivalDisplayName({
                          festivalName: event.festival.name,
                          title: event.title,
                          artistName: linkedArtistName,
                        })}
                      </h2>

                      <p className="text-sm text-muted-subtle mt-1">{t('lineupHint')}</p>
                    </div>

                    {festivalSeries && (
                      <Link
                        href={`/${locale}/festivals/${event.id}`}
                        className="text-sm text-accent hover:text-accent/80 transition shrink-0"
                      >
                        {t('exploreFestival')}
                      </Link>
                    )}
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

                {festivalSeries && (
                  <Link
                    href={`/${locale}/festivals/${event.id}`}
                    className="text-sm text-accent hover:text-accent/80 transition"
                  >
                    {t('openFestivalPage')}
                  </Link>
                )}
              </div>

              {lineup.length === 0 ? (
                <p className="py-12 text-center text-muted-subtle">{t('lineupUnavailable')}</p>
              ) : (
                <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {lineup.map((artist) => (
                    <LineupPerformerCard
                      key={
                        artist.songkick_id ||
                        artist.name
                      }
                      performer={artist}
                      locale={locale}
                      variant="row"
                      testId="event-lineup-entry"
                      onOpen={handleLineupArtistOpen}
                    />
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
