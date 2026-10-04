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

import { eventAPI } from '../../../lib/api';

import type { Locale } from '../../../i18n';

import {
  resolveLocale,
  formatEventDateRange,
} from '../../../lib/dates';

import Card from '../../../../components/ui/Card';
import LoadingState from '../../../../components/LoadingState';


interface LineupArtist {
  name: string;
  songkick_id?: string | null;
  slug?: string | null;
  url?: string | null;
  image?: string | null;
  genres?: string[];
  order: number;

  // Set by the API only when GigCrowd already has this artist. Its absence is
  // meaningful: it means there is no page to link to.
  artist_slug?: string | null;
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
  const sourceUrl = identity.official_url || identity.url;

  return (
    <div className="min-h-screen">
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
            ============================================================ */}
        <section className="mt-6 rounded-2xl border border-border bg-card-bg p-6 md:p-8">
          <p className="text-xs uppercase tracking-wide text-accent mb-3">
            {t('title')}
          </p>

          <h1 className="text-3xl md:text-5xl font-bold tracking-tight break-words">
            {festivalName}
          </h1>

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
                className="inline-flex items-center rounded-lg bg-accent px-5 py-3 text-sm font-semibold text-white hover:opacity-90 transition"
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
            ============================================================ */}
        {editions.length > 0 && (
          <section className="mt-8">
            <Card className="p-6 md:p-8">
              <h2 className="text-2xl font-bold">
                {t('editions')}
              </h2>

              <ul className="mt-6 divide-y divide-border">
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
                      (entry) =>
                        entry.event.id === event.id
                    )?.lineup.length ?? 0;

                  return (
                    <li key={event.id}>
                      <Link
                        href={`/${locale}/events/${event.id}`}
                        data-testid={`festival-edition-${event.id}`}
                        aria-current={
                          isSelected
                            ? 'true'
                            : undefined
                        }
                        className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 py-4 hover:bg-card-hover transition rounded-lg px-2 -mx-2"
                      >
                        <div className="min-w-0">
                          <p className="font-semibold truncate">
                            {event.title}
                          </p>

                          <p className="text-sm text-muted-subtle mt-1">
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

                        <div className="flex items-center gap-3 shrink-0">
                          {isSelected && (
                            <span className="text-xs font-semibold text-accent">
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
            </Card>
          </section>
        )}

        {/* ============================================================
            LINEUP
            The lineup of the edition being viewed. Entries that GigCrowd has
            an artist page for link to it; the rest are shown as names.
            ============================================================ */}
        <section className="mt-8">
          <Card className="p-6 md:p-8">
            <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-5">
              <div>
                <p className="text-xs uppercase tracking-wide text-accent mb-2">
                  {t('lineup')}
                </p>

                <h2 className="text-2xl font-bold">
                  {lineup.length > 0
                    ? t('artistsCount', {
                        count: lineup.length,
                      })
                    : t('artists')}
                </h2>
              </div>

              {lineup.length > 0 && (
                <div className="w-full md:w-72">
                  <input
                    value={query}
                    onChange={(event) =>
                      setQuery(event.target.value)
                    }
                    placeholder={t('searchPlaceholder')}
                    aria-label={t('searchPlaceholder')}
                    className="w-full rounded-lg border border-border bg-background px-4 py-3 text-sm text-foreground outline-none focus:border-accent"
                  />
                </div>
              )}
            </div>

            {filteredLineup.length === 0 ? (
              <div
                className="py-16 text-center"
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
                className="mt-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
                data-testid="festival-lineup"
              >
                {filteredLineup.map((artist) => (
                  <LineupCard
                    key={
                      artist.songkick_id ||
                      artist.artist_slug ||
                      artist.name
                    }
                    artist={artist}
                    locale={locale}
                  />
                ))}
              </div>
            )}
          </Card>
        </section>
      </main>
    </div>
  );
}

/**
 * One performer. A link when GigCrowd has the artist, plain text when it does
 * not - the alternative, an artist created on click, would put records in the
 * catalogue that nobody curated.
 */
function LineupCard({
  artist,
  locale,
}: {
  artist: LineupArtist;
  locale: Locale;
}) {
  const t = useTranslations('festivals');

  const content = (
    <>
      <div className="flex items-center gap-4">
        {artist.image ? (
          <img
            src={artist.image}
            alt=""
            loading="lazy"
            className="h-14 w-14 rounded-full object-cover shrink-0"
          />
        ) : (
          <div className="h-14 w-14 rounded-full bg-card-hover flex items-center justify-center text-xl shrink-0">
            ♪
          </div>
        )}

        <div className="min-w-0 flex-1">
          <p
            className={`font-semibold truncate ${
              artist.artist_slug
                ? 'group-hover:text-accent transition'
                : ''
            }`}
          >
            {artist.name}
          </p>

          <p className="text-xs text-muted-subtle mt-1">
            {artist.artist_slug
              ? t('openArtist')
              : t('artistNotImported')}
          </p>
        </div>

        {artist.artist_slug && (
          <span
            className="text-accent shrink-0"
            aria-hidden="true"
          >
            →
          </span>
        )}
      </div>
    </>
  );

  const className =
    'block rounded-xl border border-border bg-background/20 p-4 text-left transition';

  if (!artist.artist_slug) {
    return (
      <div
        className={className}
        data-testid="festival-lineup-entry"
      >
        {content}
      </div>
    );
  }

  return (
    <Link
      href={`/${locale}/artists/${artist.artist_slug}`}
      data-testid="festival-lineup-entry"
      className={`${className} hover:border-accent hover:bg-card-hover`}
    >
      {content}
    </Link>
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