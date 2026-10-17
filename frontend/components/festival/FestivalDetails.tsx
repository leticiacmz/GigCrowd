'use client';

/*
  A festival page's whole view, shared by the two addresses that reach it.

  A festival is addressed either by one of its dates (`/festivals/{id}`) or by
  the series it is (`/festivals/series/{seriesId}`). Both fetch the same
  response from the same service and render it here, so the same stored records
  read the same whichever door the reader came through - the fetch and the
  fallback back-link are the only things that differ, and those stay in the
  route pages.

  The view keeps two things apart, because the source keeps them apart. The
  festival is a series with a name, a canonical page and a span of dates. Each
  date is its own event with its own venue and its own lineup. So the header
  describes the festival, the editions list describes the dates, and the lineup
  shown is the one belonging to the date being viewed - not a single lineup
  borrowed from whichever date happened to be nearest.

  A lineup artist links to their GigCrowd page only when one exists. Most
  performers on a festival bill are not imported, and a link to a page that
  does not exist, or an artist created on the spot to make the link work, would
  both be worse than showing the name plainly. An entry that announced a
  Songkick id but has no page here links to the artist's import address
  instead, which is the request to run that validation - the lineup itself
  never imports and never waits on an import: pressing a name navigates, and
  the import happens on the address it lands on.
*/
import {
  useEffect,
  useMemo,
  useState,
} from 'react';

import { useRouter } from 'next/navigation';

import Link from 'next/link';
import { useTranslations } from 'next-intl';

import { eventAPI } from '../../app/lib/api';

import type { Locale } from '../../app/i18n';

import {
  formatEventDateRange,
} from '../../app/lib/dates';

import SectionHeader from '../ui/SectionHeader';
import LoadingState from '../LoadingState';
import LineupPerformerCard, {
  type LineupPerformer,
} from './LineupPerformerCard';


type LineupArtist = LineupPerformer & { order: number };

/*
  What the record says about this lineup's own enrichment - the same
  literals the response carries, kept as one spelling here. `ok` and
  `unknown` are the readings every row has always had; the rest are the
  states of the pass that reads an edition's own page for the rest of the
  bill (see `LineupEnrichmentService`).
*/
export type LineupState =
  | 'ok'
  | 'unknown'
  | 'pending'
  | 'active'
  | 'partial'
  | 'failed'
  | 'empty';

/*
  How long a `pending`/`active` state may sit untouched before it reads as
  stuck. A worker that died mid-read leaves the same state a worker that is
  still reading writes, so age is the only difference the response can
  offer - and after it, the honest thing to offer is the retry rather than
  an animation that never resolves.
*/
const WORKING_STATE_STALE_MS = 2 * 60 * 1000;

/*
  The follow-up after a retry, bounded. The button asks for one update; an
  unbounded re-read would turn that click into a polling loop, so after
  this many re-reads the page stops following and the state on screen is
  simply the one the last read returned.
*/
const MAX_POLLS = 30;
const POLL_INTERVAL_MS = 4000;

/**
 * A working state nobody has advanced for longer than the bound reads as
 * stuck.
 *
 * `pending` and `active` are written by whoever queues and whoever claims
 * the work, and a worker that dies leaves exactly the state a worker that
 * is alive writes - the response carries no liveness of its own, so the age
 * of the writing is the only difference on offer. A state with no moment at
 * all is older than any bound: nothing claims recent work for it. Once
 * stuck, the honest rendering is the retry, not an animation that never
 * resolves.
 */
function isStuckWorkingState(
  state: LineupState,
  updatedAt?: string | null,
): boolean {
  if (state !== 'pending' && state !== 'active') {
    return false;
  }

  if (!updatedAt) {
    return true;
  }

  const moment = Date.parse(updatedAt);

  return (
    Number.isNaN(moment) ||
    Date.now() - moment > WORKING_STATE_STALE_MS
  );
}

interface Venue {
  slug?: string | null;
  name?: string | null;
  city?: string | null;
  country?: string | null;
}

interface Location {
  city?: string | null;
  country?: string | null;
}

interface Edition {
  id: string;
  title: string;
  starts_at?: string | null;
  ends_at?: string | null;
  venue?: Venue | null;
  venue_slug?: string | null;
  location?: Location | null;
}

interface EditionEntry {
  event: Edition;
  lineup: LineupArtist[];

  /*
    This edition's own enrichment state, when the row carries one. Displayed
    nowhere on this view - the lineup section reports the edition being
    viewed - but part of the response, so the type says what arrives.
  */
  lineup_state?: LineupState;
  lineup_state_updated_at?: string | null;
}

interface FestivalIdentity {
  series_id: string;
  name?: string | null;
  url?: string | null;
  official_url?: string | null;
  image_url?: string | null;
  edition?: string | null;
  tracking_count?: number | null;
  editions_count: number;
  first_date?: string | null;
  last_date?: string | null;
}

export interface Festival {
  identity: FestivalIdentity;
  editions: EditionEntry[];
  selected_event_id?: string | null;
  lineup: LineupArtist[];

  /*
    Whether the shown lineup is actually held, and where the record stands
    about reading the rest of it. `unknown` is not an empty bill: the
    response refuses to claim the festival announced no performers when the
    stored record cannot say whether the source named none, the read failed,
    or it never ran - and this view says the same, rendering the lineup
    section with that state rather than presenting the empty list as a fact
    about the festival.

    The other states are the enrichment pass itself: `pending` queued,
    `active` reading, `partial` holding performers with the pass unfinished,
    `failed` asking for a retry, `empty` a finished read that announced
    nobody. None of them may hide names already stored - the section below
    shows whatever exists in every state.
  */
  lineup_state?: LineupState;

  /* When that state was last written, for the staleness reading above. */
  lineup_state_updated_at?: string | null;
}

export interface FestivalDetailsProps {
  /** The fetched response, or null while one is being fetched. */
  festival: Festival | null;

  loading: boolean;

  /** The address names no festival this server can show. */
  notFound: boolean;

  /**
   * The event id the reader came from, when the address carried one. Only a
   * fallback: the response's own selected date leads the back link, and the
   * service always resolves one.
   */
  eventId: string | null;

  locale: Locale;

  /**
   * Re-read the response from the server. The retry button uses it to follow
   * the state it just asked for; a page view on its own never calls it, so a
   * reader who pressed nothing gets exactly one read.
   */
  onReload?: () => void | Promise<void>;
}

/**
 * One festival, rendered from a response - however the reader arrived.
 */
export default function FestivalDetails({
  festival,
  loading,
  notFound,
  eventId,
  locale,
  onReload,
}: FestivalDetailsProps) {
  const router = useRouter();
  const t = useTranslations('festivals');

  const [query, setQuery] = useState('');

  /*
    The retry, and the only follow-up this page ever runs.

    Pressing the button asks the server to read the edition's own page again;
    what comes back is a state, not the finished lineup, so the page then
    re-reads the festival response - but only after a retry it issued itself,
    only while the state says work is running, and never past the bounded
    number of re-reads above. A page nobody pressed anything on reads the
    server once and stops, whatever the states are.
  */
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState(false);
  const [watching, setWatching] = useState(false);
  const [polls, setPolls] = useState(0);

  /*
    The state as it stands, with one reading applied: a `pending`/`active`
    nobody has advanced for longer than the staleness bound reads as stuck,
    because a dead worker and a working one leave the same state behind.
  */
  const rawLineupState: LineupState =
    festival?.lineup_state ?? 'unknown';
  const lineupState: LineupState = isStuckWorkingState(
    rawLineupState,
    festival?.lineup_state_updated_at
  )
    ? 'failed'
    : rawLineupState;

  useEffect(() => {
    if (!watching) {
      return;
    }

    const state = festival?.lineup_state ?? 'unknown';

    if (
      (state !== 'pending' && state !== 'active') ||
      // A working state whose moment has gone stale reads as a dead pass:
      // following it further would chase an answer nobody is writing.
      isStuckWorkingState(
        state,
        festival?.lineup_state_updated_at
      )
    ) {
      // The pass reached its answer, failed, or died. Either way this stops.
      setWatching(false);
      return;
    }

    if (polls >= MAX_POLLS) {
      setWatching(false);
      return;
    }

    const timer = setTimeout(() => {
      setPolls((count) => count + 1);
      onReload?.();
    }, POLL_INTERVAL_MS);

    return () => clearTimeout(timer);
  }, [
    watching,
    festival?.lineup_state,
    festival?.lineup_state_updated_at,
    polls,
    onReload,
  ]);

  const identity = festival?.identity;
  const editions = useMemo(
    () => festival?.editions ?? [],
    [festival]
  );
  const lineup = useMemo(
    () => festival?.lineup ?? [],
    [festival]
  );

  const filteredLineup = useMemo(() => {
    const normalized = query.trim().toLowerCase();

    if (!normalized) {
      return lineup;
    }

    return lineup.filter((artist) =>
      artist.name.toLowerCase().includes(normalized)
    );
  }, [lineup, query]);

  // The nearest date that has one. This is the festival's span, not any single
  // edition's: it answers "when does this run", which the header asks.
  const span = useMemo(() => {
    if (identity?.first_date && identity?.last_date) {
      const from = formatEventDateRange(
        identity.first_date,
        locale
      );
      const to = formatEventDateRange(
        identity.last_date,
        locale
      );

      return from === to ? from : `${from} — ${to}`;
    }

    if (identity?.first_date) {
      return formatEventDateRange(
        identity.first_date,
        locale
      );
    }

    return null;
  }, [identity, locale]);

  /*
    One retry, single-flight: a second press while the first is in flight
    does nothing rather than asking twice, and a failed request says so on
    screen instead of silently leaving the old state up.
  */
  async function handleLineupRetry() {
    const selected = festival?.selected_event_id ?? eventId;

    if (retrying || !selected) {
      return;
    }

    setRetrying(true);
    setRetryError(false);

    try {
      await eventAPI.retryLineup(selected);

      setPolls(0);
      setWatching(true);
      await onReload?.();
    } catch {
      setRetryError(true);
      setWatching(false);
    } finally {
      setRetrying(false);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingState message={t('loading')} />
      </div>
    );
  }

  if (notFound || !festival || !identity) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="text-center">
          <p className="text-muted mb-4">{t('notFound')}</p>

          <button
            type="button"
            onClick={() => router.back()}
            className="text-accent hover:text-accent/80 transition"
          >
            {t('goBack')}
          </button>
        </div>
      </div>
    );
  }

  const festivalName = identity.name || t('title');

  /*
    Rendered as an `<a href>`, so only an address a browser can open is worth
    rendering. The API validates this before sending, but rows written before
    that validation existed can still hold a relative path, and a relative
    `href` would silently become a link into GigCrowd itself instead of back
    to the source.
  */
  const candidateUrl = identity.official_url || identity.url;
  const sourceUrl =
    candidateUrl && /^https?:\/\//i.test(candidateUrl)
      ? candidateUrl
      : null;

  /*
    The date the reader is standing on, when the address named one. The
    service always resolves a selected date, so this is only a fallback for a
    response that somehow carries none.
  */
  const backTo = festival.selected_event_id ?? eventId;

  /*
    How the lineup section reads now: whether any name is stored at all,
    which state needs a note above the names, and whether the retry button
    belongs on screen. The button follows the state rather than the fetch -
    it appears for a failed or partial pass and for a finished read that
    announced nobody, the three moments a second read can change what is
    shown - and never while a fresh claim is working, because there the
    honest answer is patience, not a second request.
  */
  const storedNames = lineup.length > 0;
  const needsNote =
    storedNames &&
    (lineupState === 'pending' ||
      lineupState === 'active' ||
      lineupState === 'partial' ||
      lineupState === 'failed');
  const canRetry =
    (lineupState === 'failed' ||
      lineupState === 'partial' ||
      lineupState === 'empty') &&
    Boolean(backTo);

  const lineupNote =
    lineupState === 'pending'
      ? t('lineupQueued')
      : lineupState === 'active'
        ? t('lineupUpdating')
        : lineupState === 'partial'
          ? t('lineupPartial')
          : t('lineupFailed');

  const emptyMessage = storedNames
    ? t('noSearchMatches')
    : lineupState === 'pending' || lineupState === 'active'
      ? t('lineupUpdating')
      : lineupState === 'partial'
        ? t('lineupPartial')
        : lineupState === 'failed'
          ? t('lineupFailed')
          : lineupState === 'empty'
            ? t('lineupEmptyConfirmed')
            : t('lineupEmpty');

  const retryButton = canRetry ? (
    <button
      type="button"
      onClick={handleLineupRetry}
      disabled={retrying}
      data-testid="lineup-retry"
      className="
        shrink-0
        rounded-lg
        border
        border-border
        px-4
        py-2
        text-sm
        text-foreground
        transition
        hover:border-accent
        disabled:cursor-not-allowed
        disabled:opacity-60
      "
    >
      {retrying ? t('lineupRetrying') : t('retryLineup')}
    </button>
  ) : null;

  const retryFailure = retryError ? (
    <p className="text-sm text-red-400" data-testid="lineup-retry-error">
      {t('lineupRetryFailed')}
    </p>
  ) : null;

  return (
    <div className="min-h-screen">
      <main className="max-w-6xl mx-auto px-4 py-8">
        {backTo && (
          <Link
            href={`/${locale}/events/${backTo}`}
            className="inline-flex items-center text-sm text-accent hover:text-accent/80 transition"
          >
            {t('backToEvent')}
          </Link>
        )}

        {/* ============================================================
            HEADER / OVERVIEW
            The festival as a series. It carries no single date, because a
            festival that runs over several days does not have one.

            The eyebrow says "series" on purpose. Everything in this block
            describes the festival across all of its editions, and a reader who
            takes it for one night will misread every date below it.
            ============================================================ */}
        <section className="mt-6 rounded-2xl border border-border bg-card-bg p-6 md:p-8">
          <p className="text-xs uppercase tracking-wide text-accent mb-3">
            {t('seriesLabel')}
          </p>

          <h1 className="text-3xl md:text-5xl font-bold tracking-tight break-words">
            {festivalName}
          </h1>

          <p className="mt-3 max-w-2xl text-sm text-muted">
            {t('seriesHint')}
          </p>

          <div className="mt-7 grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-subtle mb-1">
                {t('dates')}
              </p>

              <p className="text-foreground">
                {span || t('dateUnavailable')}
              </p>
            </div>

            <div>
              <p className="text-xs uppercase tracking-wide text-muted-subtle mb-1">
                {t('editions')}
              </p>

              <p className="text-foreground">
                {identity.editions_count > 0
                  ? t('editionsCount', {
                      count: identity.editions_count,
                    })
                  : t('noEditions')}
              </p>
            </div>

            <div>
              <p className="text-xs uppercase tracking-wide text-muted-subtle mb-1">
                {t('location')}
              </p>

              <p className="text-foreground">
                {firstPlace(editions) || t('unknownCity')}
              </p>
            </div>
          </div>

          {sourceUrl && (
            <div className="mt-7">
              <a
                href={sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="
                  inline-flex
                  items-center
                  rounded-lg
                  border
                  border-border
                  px-4
                  py-2
                  text-sm
                  font-semibold
                  text-muted
                  transition-colors
                  hover:bg-card-hover
                  hover:text-foreground
                "
              >
                {t('officialWebsite')}
              </a>
            </div>
          )}
        </section>

        {/* ============================================================
            EDITIONS
            Each concrete date, as its own row linking to its own page. An
            edition is only listed when it was actually imported; none is
            inferred from a name or a year.

            The heading and its hint are what stop this reading as a list of
            separate festivals: the rows are editions of the one festival named
            above, and the selected one is marked as such.
            ============================================================ */}
        {editions.length > 0 && (
          <section className="mt-8">
            <SectionHeader
              title={t('editionsHeading')}
              count={
                <span className="text-sm text-muted-subtle">
                  {t('editionsCount', {
                    count: editions.length,
                  })}
                </span>
              }
            />

            <p className="mb-4 max-w-2xl text-sm text-muted-subtle">
              {t('editionsHint')}
            </p>

            <ul
              className="divide-y divide-border rounded-2xl border border-border bg-card-bg px-4 md:px-6"
              data-testid="festival-editions"
            >
              {editions.map(({ event }) => {
                const isSelected =
                  event.id === festival.selected_event_id;

                const dateLabel =
                  describeDates(event, locale) ??
                  t('dateUnavailable');

                const place =
                  placeOf(event) ?? t('unknownCity');

                const lineupCount =
                  editions.find(
                    (entry) => entry.event.id === event.id
                  )?.lineup.length ?? 0;

                return (
                  <li key={event.id}>
                    <Link
                      href={`/${locale}/events/${event.id}`}
                      data-testid={`festival-edition-${event.id}`}
                      aria-current={
                        isSelected ? 'true' : undefined
                      }
                      className={`
                        flex
                        flex-col
                        gap-2
                        rounded-lg
                        px-2
                        py-4
                        transition-colors
                        sm:flex-row
                        sm:items-center
                        sm:justify-between
                        sm:-mx-2
                        ${
                          isSelected
                            ? 'bg-accent/10'
                            : 'hover:bg-card-hover'
                        }
                      `}
                    >
                      <div className="min-w-0">
                        <p className="truncate font-semibold">
                          {event.title}
                        </p>

                        <p className="mt-1 text-sm text-muted-subtle">
                          {place}
                          {lineupCount > 0 && (
                            <>
                              {' • '}
                              {t('artistsCount', {
                                count: lineupCount,
                              })}
                            </>
                          )}
                        </p>
                      </div>

                      <div className="flex shrink-0 items-center gap-3">
                        {isSelected && (
                          <span
                            className={`
                              rounded-full
                              bg-accent-solid
                              px-2
                              py-0.5
                              text-[11px]
                              font-semibold
                              uppercase
                              tracking-wide
                              text-white
                            `}
                            data-testid="festival-edition-selected"
                          >
                            {t('selectedEdition')}
                          </span>
                        )}

                        <span className="text-sm text-foreground">
                          {dateLabel}
                        </span>
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {/* ============================================================
            LINEUP
            The lineup of the edition being viewed. Entries that GigCrowd has
            an artist page for link to it; the rest are shown as names.

            A lineup is the one place a festival page reads as a poster rather
            than a record, so the names lead and the grid stays dense. The hint
            says which edition the names belong to, because a festival's lineup
            genuinely differs per edition.

            `data-lineup-state` carries this lineup's own state, after the
            staleness reading: `ok`/`unknown` as always, or the pass's own
            `pending`/`active`/`partial`/`failed`/`empty` - so a test can tell
            "held, empty search" and "nothing is held" apart without reading
            the words on screen, and can see a stale working state rendered
            as the stuck pass it is.
            ============================================================ */}
        <section
          className="mt-10"
          data-lineup-state={lineupState}
        >
          <SectionHeader
            title={
              lineup.length > 0
                ? t('artistsCount', { count: lineup.length })
                : t('lineup')
            }
            action={
              lineup.length > 0 ? (
                <div className="w-44 md:w-64">
                  <input
                    value={query}
                    onChange={(event) =>
                      setQuery(event.target.value)
                    }
                    placeholder={t('searchPlaceholder')}
                    aria-label={t('searchPlaceholder')}
                    className="
                      w-full
                      rounded-lg
                      border
                      border-border
                      bg-background
                      px-3
                      py-2
                      text-sm
                      text-foreground
                      outline-none
                      focus:border-accent
                    "
                  />
                </div>
              ) : undefined
            }
          />

          <p className="mb-5 max-w-2xl text-sm text-muted-subtle">
            {t('lineupHint')}
          </p>

          {needsNote && (
            <div
              className="
                mb-5
                flex
                flex-col
                gap-3
                rounded-2xl
                border
                border-border
                bg-card-bg
                px-4
                py-4
                sm:flex-row
                sm:items-center
                sm:justify-between
              "
              data-testid="lineup-status"
            >
              <div>
                <p className="text-sm text-muted">{lineupNote}</p>
                {retryFailure}
              </div>
              {retryButton}
            </div>
          )}

          {filteredLineup.length === 0 ? (
            <div
              className="rounded-2xl border border-border bg-card-bg py-16 text-center"
              data-testid="festival-lineup"
            >
              <div className="flex flex-col items-center gap-4 px-4">
                <p className="text-muted-subtle">{emptyMessage}</p>
                {canRetry && !needsNote && (
                  <div className="flex flex-col items-center gap-2">
                    {retryButton}
                    {retryFailure}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div
              className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5"
              data-testid="festival-lineup"
            >
              {filteredLineup.map((artist) => (
                <LineupPerformerCard
                  key={
                    artist.songkick_id ||
                    artist.artist_slug ||
                    artist.name
                  }
                  performer={artist}
                  locale={locale}
                />
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

/** A date range for one edition, or `null` when the source gave no date. */
function describeDates(
  event: Edition,
  locale: Locale,
): string | null {
  if (!event.starts_at && !event.ends_at) {
    return null;
  }

  if (!event.ends_at) {
    return formatEventDateRange(
      event.starts_at,
      locale
    );
  }

  const from = formatEventDateRange(
    event.starts_at ?? event.ends_at,
    locale
  );
  const to = formatEventDateRange(
    event.ends_at,
    locale
  );

  return from === to ? from : `${from} — ${to}`;
}

/** Where an edition is held, from whichever field states it. */
function placeOf(event: Edition): string | null {
  const city =
    event.location?.city || event.venue?.city || null;
  const country =
    event.location?.country ||
    event.venue?.country ||
    null;

  if (city && country) {
    return `${city}, ${country}`;
  }

  return city || country || event.venue?.name || null;
}

/** The location of the festival, taken from the editions that state one. */
function firstPlace(
  editions: EditionEntry[],
): string | null {
  for (const { event } of editions) {
    const place = placeOf(event);

    if (place) {
      return place;
    }
  }

  return null;
}
