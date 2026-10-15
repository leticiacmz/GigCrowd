'use client';

/**
 * A festival, and the concrete dates it runs on.
 *
 * The page keeps two things apart, because the source keeps them apart. The
 * festival is a series with a name, a canonical page and a span of dates. Each
 * date is its own event with its own venue and its own lineup. So the header
 * describes the festival, the editions list describes the dates, and the lineup
 * shown is the one belonging to the date being viewed - not a single lineup
 * borrowed from whichever date happened to be nearest.
 *
 * A lineup artist links to their GigCrowd page only when one exists. Most
 * performers on a festival bill are not imported, and a link to a page that
 * does not exist, or an artist created on the spot to make the link work, would
 * both be worse than showing the name plainly.
 */
import {
  useCallback,
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

import { artistAPI, eventAPI } from '../../../lib/api';

import type { Locale } from '../../../i18n';

import {
  resolveLocale,
  formatEventDateRange,
} from '../../../lib/dates';
import { createArtistOpener } from '../../../lib/artistSync';

import SectionHeader from '../../../../components/ui/SectionHeader';
import ArtistSyncLoading from '../../../../components/ui/ArtistSyncLoading';
import LoadingState from '../../../../components/LoadingState';
import LineupPerformerCard, {
  type LineupPerformer,
} from '../../../../components/festival/LineupPerformerCard';


type LineupArtist = LineupPerformer & { order: number };

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

interface Festival {
  identity: FestivalIdentity;
  editions: EditionEntry[];
  selected_event_id?: string | null;
  lineup: LineupArtist[];
}

export default function FestivalPage() {
  const router = useRouter();
  const params = useParams();
  const locale = resolveLocale(params.locale as string);
  const eventId = params.id as string;
  const t = useTranslations('festivals');

  const [festival, setFestival] = useState<Festival | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [query, setQuery] = useState('');

  const load = useCallback(async () => {
    setLoading(true);

    try {
      const data = await eventAPI.getFestival(eventId);

      setFestival(data);
      setNotFound(false);
    } catch {
      // A 404 here is a real answer: the event is not a festival date, so there
      // is no festival page to show rather than a page waiting to load.
      setFestival(null);
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

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
    Pressing a lineup name that has no page here yet starts the on-demand
    import - same single-operation rule as the event page: one overlay, and
    the opener deduplicates by Songkick id while a call is in flight. The
    entry's own `slug` field is Songkick's namespace and is never looked up;
    the Songkick id is the identity.
  */
  const [openingArtist, setOpeningArtist] = useState<{
    phase: 'searching' | 'importing';
    performer: LineupArtist;
  } | null>(null);
  const [openFailure, setOpenFailure] = useState<{
    reason: 'failed' | 'unidentifiable';
    performer: LineupArtist;
  } | null>(null);

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
    if (openingArtist) {
      return;
    }

    setOpenFailure(null);
    setOpeningArtist({ phase: 'searching', performer });

    artistOpener
      .open(
        {
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

  return (
    <div className="min-h-screen">
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
          href={`/${locale}/events/${festival.selected_event_id ?? eventId}`}
          className="inline-flex items-center text-sm text-accent hover:text-accent/80 transition"
        >
          {t('backToEvent')}
        </Link>

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
            ============================================================ */}
        <section className="mt-10">
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

          {filteredLineup.length === 0 ? (
            <div
              className="rounded-2xl border border-border bg-card-bg py-16 text-center"
              data-testid="festival-lineup"
            >
              <p className="text-muted-subtle">
                {lineup.length === 0
                  ? t('lineupEmpty')
                  : t('noSearchMatches')}
              </p>
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
                  onOpen={handleLineupArtistOpen}
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