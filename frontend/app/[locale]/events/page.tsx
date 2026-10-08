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
 * An empty box lists what is on for a signed-out reader, exactly as it
 * always has: upcoming shows, genre filter and cursor included. For a signed-in
 * reader the empty box is the personalized list of the shows of the artists
 * they follow - a different section, held apart below, that never borrows a
 * row from this one and is never answered with general discovery.
 *
 * A typed query is a *lookup rather than a browse* - it reaches shows that
 * have already happened, because searching "Mada" and being told "nothing"
 * when the editions are held here would be the box lying about what it can
 * see.
 *
 * Searching imports nothing. Picking an act is what imports it, and that is a
 * separate, deliberate action.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { artistAPI, eventAPI, searchAPI } from '../../lib/api';
import {
  getCurrentPath,
  getLoginPath,
  isAuthenticated,
} from '../../lib/auth';
import type {
  EventSearchCursor,
  EventSearchResponse,
  EventSearchRow,
} from '@/app/types/eventSearch';
import type { ArtistSearchResult } from '@/app/types/unifiedSearch';

import Input from '../../../components/ui/Input';
import Button from '../../../components/ui/Button';
import Select from '../../../components/ui/Select';
import ArtistCard from '../../../components/ArtistCard';
import EmptyState from '../../../components/EmptyState';
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
  const [searchLoading, setSearchLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  /*
    The answer section, and whether there is one. It holds the rows a
    submitted query produced - and, for a signed-out reader, the public
    browse list. A signed-in reader who has asked nothing has no answer
    section at all: what they see is the personalized list below, which has
    its own state entirely.
  */
  const [answerActive, setAnswerActive] = useState(false);

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
    Whether there is a session at all, read once on arrival. It decides which
    sections exist: signed in gets the personalized list as the default view;
    signed out gets the public browse list and an invitation to sign in.
  */
  const [signedIn, setSignedIn] = useState<boolean | null>(null);

  /*
    The personalized list, held entirely apart from the search above it: its
    own rows, its own cursor, its own status, and `followedCount` - how many
    artists the reader follows - which is what lets the empty state say "you
    follow nobody" rather than "nobody you follow has a show ahead".
  */
  const [followedRows, setFollowedRows] = useState<EventSearchRow[]>([]);
  const [followedTotal, setFollowedTotal] = useState(0);
  const [followedCursor, setFollowedCursor] =
    useState<EventSearchCursor | null>(null);
  const [followedCount, setFollowedCount] = useState<number | null>(null);
  const [followedStatus, setFollowedStatus] = useState<
    'idle' | 'loading' | 'ready' | 'error'
  >('idle');
  const [followedLoadingMore, setFollowedLoadingMore] = useState(false);

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
    The personalized list, and nothing else.

    Strictly the artists this reader follows: the same rows, the same
    provenance rules, the same soonest-first ordering and the same cursor as
    the browse list, narrowed to their follows. An empty answer stays empty -
    it is never replaced by general discovery, because a section that
    silently swaps in artists the reader does not follow is no longer the
    reader's section. `following_count` rides along even on the empty page,
    which is what lets the UI say *which* empty this is.
  */
  const loadFollowing = useCallback(
    async (options?: { before?: string; beforeId?: string }) => {
      const paging = Boolean(options?.before);

      if (!paging) {
        setFollowedStatus('loading');
      }

      try {
        const data: EventSearchResponse =
          await eventAPI.followingEvents({
            limit: PAGE_SIZE,
            before: options?.before,
            beforeId: options?.beforeId,
          });

        const page = data.events ?? [];

        setFollowedRows((current) => {
          if (!paging) {
            return page;
          }

          // Merged by identity: two pages can overlap when an event is
          // imported between two reads, and a duplicated row in a list of
          // dates reads as two shows.
          const known = new Set(current.map((row) => row.id));
          return [...current, ...page.filter((row) => !known.has(row.id))];
        });
        setFollowedTotal(data.total ?? 0);
        setFollowedCursor(data.next_cursor ?? null);
        setFollowedCount(
          typeof data.following_count === 'number'
            ? data.following_count
            : null
        );
        setFollowedStatus('ready');
      } catch (err) {
        if (
          (err as { response?: { status?: number } })?.response?.status ===
          401
        ) {
          // The session died mid-visit. The signed-out presentation is the
          // honest one now - the public list and an invitation - rather
          // than a personalized section that can no longer be fetched.
          setSignedIn(false);
          setFollowedStatus('idle');

          try {
            const data = await eventAPI.searchEvents({ limit: PAGE_SIZE });

            setRows(data.events ?? []);
            setTotal(data.total ?? 0);
            setCursor(data.next_cursor ?? null);
            setAnswerActive(true);
          } catch {
            setRows([]);
            setTotal(0);
            setCursor(null);
            setAnswerActive(true);
          }

          return;
        }

        // A paging failure keeps the cursor where it was, so trying again
        // asks for the same rows rather than skipping them; a first-page
        // failure says so instead of showing an empty list as if it were
        // the answer.
        if (!paging) {
          setFollowedStatus('error');
        }
      }
    },
    []
  );

  /*
    One box, two questions behind it - and neither answer is ever mixed into
    the other.

    With text, the box is a lookup: one request to the unified search returns
    the catalogue's matches and Songkick's acts together, and the type of each
    result is read from which field it arrived in. A genre is the same kind of
    question about the catalogue as a lookup, so it answers here too. Neither
    touches the personalized section below: that section is about who the
    reader follows, not about what is in the box.

    With neither text nor genre, the request is the browse list - and only a
    signed-out reader has one. For a signed-in reader the default view is the
    personalized section, so an empty submit re-asks *that* rather than
    answering with the general list they did not ask for.
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
      const wantedGenre = (options.genre ?? '').trim();

      try {
        if (isLookup) {
          const data = await searchAPI.unifiedSearch({
            q: text,
            genre: options.genre,
            limit: PAGE_SIZE,
            before: options.before,
            beforeId: options.beforeId,
          });

          setAnswerActive(true);
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
        } else if (wantedGenre) {
          const data = await eventAPI.searchEvents({
            genre: options.genre,
            limit: PAGE_SIZE,
            before: options.before,
            beforeId: options.beforeId,
          });

          setAnswerActive(true);
          setRows(data.events ?? []);
          setTotal(data.total ?? 0);
          setCursor(data.next_cursor ?? null);
          setArtists([]);
          setArtistError(null);
        } else if (signedIn) {
          /*
            The personalized section *is* the answer to "what is on" for a
            signed-in reader - re-asked here, and never answered with the
            general list everyone else gets.
          */
          setAnswerActive(false);
          setRows([]);
          setTotal(0);
          setCursor(null);
          setArtists([]);
          setArtistError(null);

          if (!options.before) {
            await loadFollowing();
          }
        } else {
          const data = await eventAPI.searchEvents({
            limit: PAGE_SIZE,
            before: options.before,
            beforeId: options.beforeId,
          });

          setAnswerActive(true);
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
      }
    },
    [t, signedIn, loadFollowing]
  );

  /*
    The first section is chosen once, on arrival, by whether there is a
    session - and only then.

    A signed-in reader opens on the personalized list and nothing else: it is
    the page's primary experience, so it is fetched straight away rather than
    after a submit. A signed-out reader opens on the public browse list,
    which is the answer that has something to say before anything is typed.
    Searching later never changes which section is the personalized one.

    The ref keeps this a single arrival even though `runSearch` is rebuilt
    when the session is read (its identity changes with `signedIn`).
  */
  const arrived = useRef(false);

  useEffect(() => {
    if (arrived.current) {
      return;
    }

    arrived.current = true;

    const active = isAuthenticated();
    setSignedIn(active);

    if (active) {
      loadFollowing();
      return;
    }

    setSearchLoading(true);

    runSearch({}).finally(() => setSearchLoading(false));
  }, [runSearch, loadFollowing]);

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
        sent may not change where the next page comes from. This button only
        ever pages the answer section; the personalized list pages from its
        own endpoint, since it is a different result set rather than a filter
        over this one.
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

  /*
    The personalized list's own "more". It pages from the followed endpoint
    alone - a different result set, a different cursor, and never the search
    box's - so the two lists on one page can advance independently.
  */
  async function loadMoreFollowing() {
    if (!followedCursor || followedLoadingMore) {
      return;
    }

    setFollowedLoadingMore(true);

    try {
      await loadFollowing({
        before: followedCursor.date,
        beforeId: followedCursor.id,
      });
    } finally {
      setFollowedLoadingMore(false);
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

        {/*
          Boot: while the session is being read, while the signed-in default
          view (the personalized list) is still arriving, and while a
          signed-out reader's first public list is still coming. Search
          activity never hides the personalized section - each section
          reports its own loading below.
        */}
        {signedIn === null ||
        (signedIn === true && followedStatus === 'loading') ||
        (signedIn === false && searchLoading && !answerActive) ? (
          <LoadingState message={t('searching')} />
        ) : (
          <>
            {/*
              The answer: what the box was asked, and nothing else. It sits
              above the personalized section and never borrows rows from it.
              A signed-in reader who has asked nothing has no answer section
              at all - their default view is the list below.
            */}
            {answerActive && (
              <section aria-labelledby="event-results-heading">
                {/*
                  The second of the two groups a lookup answers with.
                  "Marina Sena" is an artist and a list of dates, and a reader
                  has to be able to tell which half of the page they are
                  looking at without reading every row. The heading sits above
                  whatever `rows` holds, festival editions included, because a
                  festival edition *is* an event with its edition semantics
                  kept by the badge below rather than a third dataset.
                */}
                <h2
                  id="event-results-heading"
                  className="mb-3 text-lg font-semibold"
                  data-testid="event-search-section"
                >
                  {tEvents('eventsResults')}
                </h2>

                {searchLoading && rows.length === 0 ? (
                  <LoadingState message={t('searching')} />
                ) : rows.length === 0 ? (
                  <div
                    className="py-16 text-center"
                    data-testid="event-search-empty"
                  >
                    <p className="text-muted">{tEvents('noResults')}</p>

                    {/*
                      Said only for a query that found nothing at all, and
                      only for a query: "what is on" with no shows ahead is a
                      different answer, and neither case is helped by a note
                      about venues.
                    */}
                    {activeQuery && artists.length === 0 && !artistError && (
                      <p className="mt-2 text-sm text-muted-subtle">
                        {tEvents('noResultsHint')}
                      </p>
                    )}
                  </div>
                ) : (
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
                )}

                {cursor && rows.length > 0 && (
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
              </section>
            )}

            {/*
              The personalized section - the reader's follows and only their
              follows. No fallback to discovery when it is empty; the count
              behind it says *which* empty it is. Below the answer section so
              a search never pushes the reader's own list around, and the
              only thing on the page when there is no answer above it.
            */}
            {signedIn ? (
              <section
                className={answerActive ? 'mt-10' : ''}
                aria-labelledby="following-heading"
                data-testid="following-section"
              >
                <h2
                  id="following-heading"
                  className="mb-3 text-lg font-semibold"
                  data-testid="following-heading"
                >
                  {tEvents('followingResults')}
                </h2>

                {followedStatus === 'error' ? (
                  <p
                    className="py-8 text-center text-sm text-muted"
                    data-testid="following-error"
                  >
                    {t('searchError')}
                  </p>
                ) : followedRows.length === 0 ? (
                  <EmptyState
                    icon={followedCount === 0 ? '💫' : '🎵'}
                    title={
                      followedCount === 0
                        ? tEvents('followNoneTitle')
                        : tEvents('followNoShows')
                    }
                    description={
                      followedCount === 0
                        ? tEvents('followNoneHint')
                        : tEvents('followNoShowsHint')
                    }
                  />
                ) : (
                  <ul
                    className="space-y-3"
                    data-testid="following-results"
                    data-total={followedTotal}
                  >
                    {followedRows.map((row) => (
                      <li key={row.id}>
                        <EventResultRow
                          row={row}
                          locale={locale}
                        />
                      </li>
                    ))}
                  </ul>
                )}

                {followedCursor && (
                  <div className="mt-6 flex justify-center">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={loadMoreFollowing}
                      disabled={followedLoadingMore}
                      data-testid="following-more"
                    >
                      {followedLoadingMore
                        ? tEvents('loadingMore')
                        : tEvents('more', {
                            shown: followedRows.length,
                            total: followedTotal,
                          })}
                    </Button>
                  </div>
                )}
              </section>
            ) : (
              /*
                The signed-out counterpart of the personalized section: an
                invitation instead of a list that could only be wrong. Public
                browsing stays above it, and this leaks nothing - it is shown
                to everyone without a session, identically.
              */
              <section
                className={answerActive ? 'mt-10' : ''}
                data-testid="following-invitation"
              >
                <div className="rounded-xl border border-border bg-card-hover px-5 py-6 text-center">
                  <h2 className="mb-2 text-lg font-semibold">
                    {tEvents('inviteTitle')}
                  </h2>

                  <p className="mx-auto mb-4 max-w-md text-sm text-muted">
                    {tEvents('inviteBody')}
                  </p>

                  <Link href={getLoginPath(locale, getCurrentPath())}>
                    <Button
                      variant="outlineGradient"
                      size="sm"
                      data-testid="following-invitation-login"
                    >
                      {tEvents('inviteAction')}
                    </Button>
                  </Link>
                </div>
              </section>
            )}
          </>
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
