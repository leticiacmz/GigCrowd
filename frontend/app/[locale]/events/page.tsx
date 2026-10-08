'use client';

/**
 * The events catalogue, and the one search box.
 *
 * Two things this page deliberately does not do.
 *
 * It does not infer a genre from an event's title. "Rock in Rio" and "Boiler
 * Room" are places, not genres, and a filter that reads them as genres returns
 * confident nonsense. The genre list is built from what artists say about
 * themselves, so it only ever offers real genres.
 *
 * It does not filter in the browser. Text and genre are sent together and the
 * server does both in one query, because a page that was sliced before the
 * filter ran would show a count that disagrees with the list under it and would
 * make "next page" skip rows.
 *
 * It also does not ask the reader which source to search. "Marina Sena", "Mada"
 * and "Espaço Unimed" are one question, so the box asks it once and the answer
 * says what each result is: an act from Songkick, a show from the catalogue,
 * and among the shows, festival editions. One request reaches the server for
 * that answer, and the reader never has to know it is two questions underneath.
 *
 * An empty box lists what is on, exactly as before: upcoming shows, genre
 * filter and cursor included. A typed query is a *lookup rather than a browse*
 * - it reaches shows that have already happened, because searching "Mada" and
 * being told "nothing" when the editions are held here would be the box lying
 * about what it can see.
 *
 * Searching imports nothing. Picking an act is what imports it, and that is a
 * separate, deliberate action.
 */

import {
  useCallback,
  useEffect,
  useState,
} from 'react';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { artistAPI, eventAPI, searchAPI } from '../../lib/api';
import type {
  EventSearchCursor,
  EventSearchRow,
} from '@/app/types/eventSearch';
import type { ArtistSearchResult } from '@/app/types/unifiedSearch';

import Input from '../../../components/ui/Input';
import Button from '../../../components/ui/Button';
import Select from '../../../components/ui/Select';
import ArtistCard from '../../../components/ArtistCard';
import LoadingState from '../../../components/LoadingState';

import { formatEventDateRange } from '../../lib/dates';

const PAGE_SIZE = 20;

export default function EventsPage() {
  const t = useTranslations('artists');
  const tEvents = useTranslations('eventSearch');
  const params = useParams();
  const router = useRouter();
  const locale = (params?.locale as string) || 'en';

  const [query, setQuery] = useState('');
  const [genre, setGenre] = useState('');

  const [genres, setGenres] = useState<
    { name: string; artists: number }[]
  >([]);

  const [rows, setRows] = useState<EventSearchRow[]>([]);
  const [total, setTotal] = useState(0);
  const [cursor, setCursor] = useState<EventSearchCursor | null>(null);
  const [searchLoading, setSearchLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  /*
    The artist half of the box: the acts found for the query, and import when
    one is picked. Searching never imports; picking is the deliberate action.
  */
  const [artists, setArtists] = useState<ArtistSearchResult[]>([]);
  const [importingArtistId, setImportingArtistId] = useState<string | null>(
    null
  );
  const [artistError, setArtistError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  /*
    What the list on screen is answering: the empty string for "what is on",
    the submitted text for a lookup. Held apart from `query` - what is in the
    box - because a reader may type without submitting, and the empty state
    must describe the answer they got rather than the words never sent.
  */
  const [activeQuery, setActiveQuery] = useState('');

  /*
    Read once. The genre list comes from artist metadata and does not change as
    pages load, so fetching it per keystroke would be a request that always
    returns the same answer.
  */
  useEffect(() => {
    let cancelled = false;

    async function loadGenres() {
      try {
        const data = await eventAPI.getEventGenres();

        if (!cancelled) {
          setGenres(data.genres ?? []);
        }
      } catch {
        if (!cancelled) {
          setGenres([]);
        }
      }
    }

    loadGenres();

    return () => {
      cancelled = true;
    };
  }, []);

  /*
    One list, two questions behind it.

    With text, the box is a lookup: one request to the unified search returns
    the catalogue's matches and Songkick's acts together, and the type of each
    result is read from which field it arrived in. Without text it is the
    browse list it has always been - upcoming shows, upcoming-only, cursor
    and all - so "what is on" does not start reporting last year's dates
    because somebody cleared the box.
  */
  const runSearch = useCallback(
    async (options: {
      q?: string;
      genre?: string;
      before?: string;
      beforeId?: string;
    }) => {
      const text = (options.q ?? '').trim();
      const isLookup = text.length > 0;

      try {
        if (isLookup) {
          const data = await searchAPI.unifiedSearch({
            q: text,
            genre: options.genre,
            limit: PAGE_SIZE,
            before: options.before,
            beforeId: options.beforeId,
          });

          setRows(data.events ?? []);
          setTotal(data.total ?? 0);
          setCursor(data.next_cursor ?? null);

          /*
            The acts are taken only from a first page. Paging is not a new
            question about who is playing, and re-asking would swap the cards
            under the reader while they are reading dates.
          */
          if (!options.before) {
            setArtists(data.artists ?? []);
            setArtistError(
              data.artists_unavailable ? t('searchError') : null
            );
          }
        } else {
          const data = await eventAPI.searchEvents({
            genre: options.genre,
            limit: PAGE_SIZE,
            before: options.before,
            beforeId: options.beforeId,
          });

          setRows(data.events ?? []);
          setTotal(data.total ?? 0);
          setCursor(data.next_cursor ?? null);
          setArtists([]);
          setArtistError(null);
        }
      } catch {
        setRows([]);
        setTotal(0);
        setCursor(null);

        if (isLookup) {
          setArtists([]);
          setArtistError(t('searchError'));
        }
      } finally {
        setActiveQuery(text);
        setHasSearched(true);
      }
    },
    [t]
  );

  /*
    The first page is loaded on arrival, not on the first submit.

    A page of "what is on" that opens on an empty state and asks the reader to
    press a button to find out what is on has the question and the answer the
    wrong way round. It also means the list, the count above it and the genre
    filter all describe the same thing from the first paint.
  */
  useEffect(() => {
    setSearchLoading(true);

    runSearch({}).finally(() => setSearchLoading(false));
  }, [runSearch]);

  function submit(e: React.FormEvent) {
    e.preventDefault();

    setSearchLoading(true);

    /*
      Both filters go into one request. Sending them separately, or letting the
      client narrow a page it already has, is what makes a count and a list
      disagree.
    */
    runSearch({
      q: query.trim() || undefined,
      genre: genre || undefined,
    }).finally(() => setSearchLoading(false));
  }

  function applyGenre(value: string) {
    setGenre(value);
    setSearchLoading(true);

    runSearch({
      q: query.trim() || undefined,
      genre: value || undefined,
    }).finally(() => setSearchLoading(false));
  }

  async function loadMore() {
    if (!cursor || loadingMore) {
      return;
    }

    setLoadingMore(true);

    try {
      /*
        The *submitted* query decides the endpoint, not what is in the box
        now: paging continues the list on screen, so a word typed but never
        sent may not change where the next page comes from.
      */
      const data = activeQuery
        ? await searchAPI.unifiedSearch({
            q: activeQuery,
            genre: genre || undefined,
            limit: PAGE_SIZE,
            before: cursor.date,
            beforeId: cursor.id,
          })
        : await eventAPI.searchEvents({
            genre: genre || undefined,
            limit: PAGE_SIZE,
            before: cursor.date,
            beforeId: cursor.id,
          });

      /*
        Merged by identity. Two pages can overlap if an event is imported between
        two reads, and a duplicated row in a list of dates reads as two shows.
      */
      const known = new Set(rows.map((row) => row.id));

      setRows((current) => [
        ...current,
        ...(data.events ?? []).filter((row) => !known.has(row.id)),
      ]);

      setCursor(data.next_cursor ?? null);
    } catch {
      // The cursor is left where it was, so trying again asks for the same rows
      // rather than skipping them.
    } finally {
      setLoadingMore(false);
    }
  }

  async function selectArtist(artist: ArtistSearchResult) {
    if (importingArtistId) {
      return;
    }

    try {
      setArtistError(null);

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
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? t('importError');

      setArtistError(detail);
    } finally {
      setImportingArtistId(null);
    }
  }

  const isImporting = importingArtistId !== null;

  return (
    <div className="min-h-screen">
      <main className="mx-auto max-w-5xl px-4 py-8">
        <h1 className="mb-2 text-[28px] font-bold">
          {tEvents('title')}
        </h1>

        <p className="mb-6 text-sm text-muted">
          {tEvents('subtitle')}
        </p>

        <form
          onSubmit={submit}
          className="mb-6"
          data-testid="event-search-form"
        >
          {/*
            Stacked on a phone, side by side above it. The genre select is a
            native control on purpose: on a phone it opens the platform's own
            wheel, which is the one picker a thumb can actually use.
          */}
          <div className="flex flex-col gap-3 sm:flex-row">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={tEvents('unifiedPlaceholder')}
              aria-label={tEvents('searchLabel')}
              className="flex-1"
              disabled={isImporting}
              data-testid="event-search-input"
            />

            <label
              className="sr-only"
              htmlFor="event-genre-select"
            >
              {tEvents('genreLabel')}
            </label>

            <Select
              id="event-genre-select"
              value={genre}
              onChange={(e) => applyGenre(e.target.value)}
              className="sm:w-56"
              data-testid="event-genre-select"
              aria-label={tEvents('genreLabel')}
              options={[
                { key: '', label: tEvents('genreAll') },
                ...genres.map((row) => ({
                  key: row.name,
                  label: `${row.name} (${row.artists})`,
                })),
              ]}
            />

            <Button
              type="submit"
              disabled={searchLoading || isImporting}
              className="shrink-0"
              data-testid="event-search-submit"
            >
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

        {artistError && (
          <div
            role="alert"
            className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
            data-testid="artist-search-error"
          >
            {artistError}
          </div>
        )}

        {/*
          The acts the query named, ahead of the shows: "Marina Sena" is a
          person first and a list of dates second, and the act is what a reader
          opens - or imports, when GigCrowd has never heard of them.

          Shown only when there are any. A grid of nothing above a list of
          shows would be noise, and "no artists found" is not the interesting
          half of a search that found events.
        */}
        {artists.length > 0 && (
          <section className="mb-8" data-testid="artist-search-section">
            <h2 className="mb-3 text-lg font-semibold">
              {tEvents('artistsResults')}
            </h2>

            <div
              className={[
                'grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3',
                isImporting ? 'pointer-events-none opacity-60' : '',
              ].join(' ')}
              data-testid="artist-search-results"
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
          </section>
        )}

        {isImporting && <LoadingState message={t('importing')} />}

        {searchLoading && rows.length === 0 ? (
          <LoadingState message={t('searching')} />
        ) : rows.length === 0 && hasSearched ? (
          <div
            className="py-16 text-center"
            data-testid="event-search-empty"
          >
            <p className="text-muted">{tEvents('noResults')}</p>

            {/*
              Said only for a query that found nothing at all, and only for a
              query: "what is on" with no shows ahead is a different answer,
              and neither case is helped by a note about venues.
            */}
            {activeQuery && artists.length === 0 && !artistError && (
              <p className="mt-2 text-sm text-muted-subtle">
                {tEvents('noResultsHint')}
              </p>
            )}
          </div>
        ) : (
          <>
            {/*
              The second of the two groups a lookup answers with. "Marina
              Sena" is an artist and a list of dates, and a reader has to be
              able to tell which half of the page they are looking at without
              reading every row. The heading is data-driven: it sits above
              whatever `rows` holds, festival editions included, because a
              festival edition *is* an event with its edition semantics kept
              by the badge below rather than a third dataset.
            */}
            <h2
              className="mb-3 text-lg font-semibold"
              data-testid="event-search-section"
            >
              {tEvents('eventsResults')}
            </h2>

            <ul
              className="space-y-3"
              data-testid="event-search-results"
              data-total={total}
            >
              {rows.map((row) => (
                <li key={row.id}>
                  <EventResultRow
                    row={row}
                    locale={locale}
                  />
                </li>
              ))}
            </ul>
          </>
        )}

        {cursor && (
          <div className="mt-6 flex justify-center">
            <Button
              type="button"
              variant="outline"
              onClick={loadMore}
              disabled={loadingMore}
              data-testid="event-search-more"
            >
              {loadingMore
                ? tEvents('loadingMore')
                : tEvents('more', {
                    shown: rows.length,
                    total,
                  })}
            </Button>
          </div>
        )}
      </main>
    </div>
  );
}

/**
 * One search result.
 *
 * A row rather than a card: the point of a search is to scan a list, so the
 * date and the venue sit beside the title instead of inside it. The date is the
 * first thing a reader is looking for, and a festival's full range is shown
 * rather than its opening night.
 */
function EventResultRow({
  row,
  locale,
}: {
  row: EventSearchRow;
  locale: string;
}) {
  const tCard = useTranslations('eventCard');

  const from = row.starts_at
    ? formatEventDateRange(row.starts_at, locale as never)
    : null;

  const to =
    row.ends_at && row.starts_at !== row.ends_at
      ? formatEventDateRange(row.ends_at, locale as never)
      : null;

  const place =
    [row.venue?.name, row.venue?.city || row.location?.city]
      .filter(Boolean)
      .join(' · ') || null;

  /*
   * The entity this row is. Derived from the two fields the catalogue already
   * carries - the `festival` block the API only writes when a series id backs
   * it, and `event_type` - so a festival edition that has not been tied to a
   * series yet still reads as one instead of silently becoming a concert.
   */
  const isFestivalRow =
    Boolean(row.festival?.series_id) ||
    row.event_type === 'FestivalInstance';

  /*
   * The trusted artist relationship, surfaced as slugs rather than as nested
   * links: the whole row is already the link to the event, and GigCrowd only
   * ever fills `artists` with artists that exist, so the identity on offer is
   * a real one.
   */
  const artistSlugs = row.artists
    .map((artist) => artist.slug)
    .filter(Boolean)
    .join(',');

  return (
    <Link
      href={`/${locale}/events/${row.id}`}
      className="
        flex
        flex-col
        gap-1
        rounded-xl
        border
        border-hairline-strong
        bg-surface-raised/40
        p-4
        transition
        hover:border-accent
        focus-ring
        sm:flex-row
        sm:items-center
        sm:justify-between
        sm:gap-4
      "
      data-testid="event-search-row"
      data-entity-type={isFestivalRow ? 'festival_edition' : 'event'}
      data-artist-slugs={artistSlugs}
    >
      <span className="min-w-0 flex-1">
        <span className="block font-medium text-foreground">
          {row.title}
        </span>

        <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-subtle">
          <span
            className="
              rounded
              border
              border-border
              px-1.5
              py-px
              text-[11px]
              font-medium
              uppercase
              tracking-wide
              text-muted
            "
            data-testid="event-search-type"
          >
            {isFestivalRow ? tCard('festival') : tCard('concert')}
          </span>

          {row.artists.length > 0 && (
            <span>{row.artists.map((a) => a.name).join(', ')}</span>
          )}

          {row.festival?.name && (
            <span
              className="
                rounded
                border
                border-accent/40
                px-1.5
                py-px
                text-[11px]
                font-medium
                uppercase
                tracking-wide
                text-accent-text
              "
              data-testid="event-search-festival"
            >
              {row.festival.name}
            </span>
          )}

          {place && <span>{place}</span>}
        </span>
      </span>

      {from && (
        <span
          className="shrink-0 text-sm text-muted sm:text-right"
          data-testid="event-search-date"
        >
          {from}
          {to ? ` — ${to}` : ''}
        </span>
      )}
    </Link>
  );
}
