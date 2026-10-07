'use client';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';

import { userAPI } from '@/app/lib/api';
import {
  formatEventSchedule,
  intlTag,
} from '@/app/lib/dates';
import type { Locale } from '@/app/i18n';
import type {
  ProfileEvent,
  ProfileEventCursor,
  ProfileFestival,
  ProfileReview,
  ProfileSeenArtist,
  ProfileShowCounts,
  ProfileShowStatus,
} from '@/app/types/profile';
import ReviewCard from '@/components/ReviewCard';
import ShowCalendar from '@/components/profile/ShowCalendar';

import Avatar from '@/components/ui/Avatar';
import Card from '@/components/ui/Card';
import SectionHeader from '@/components/ui/SectionHeader';
import LoadingState from '@/components/LoadingState';
import EmptyState from '@/components/EmptyState';

export type Panel =
  | 'reviews'
  | 'events'
  | 'festivals'
  | 'artists'
  | 'followers'
  | 'following'
  | null;

/**
 * How many rows a panel shows inline.
 *
 * The figure in the header is the real total from the endpoint; this is only how
 * much of it is worth rendering under it, so the number never quietly changes
 * meaning between the header and the list.
 */
const PREVIEW_LIMIT = 3;

/**
 * How many shows one batch of the scrollable diary carries.
 *
 * Large enough that a reader with a long history sees a screenful of it before
 * reaching for more, small enough that the first batch does not hold up the page.
 */
const PAGE_SIZE = 40;

interface ProfilePanelProps {
  panel: Exclude<Panel, null>;
  username: string;
  locale: Locale;
}

/**
 * The rows behind one figure on a profile.
 *
 * A panel is loaded only when it is opened, so a profile costs one request
 * until someone asks a question. Each concert panel has exactly one request
 * behind it, and the two social panels share the connections endpoint.
 */
export default function ProfilePanel({
  panel,
  username,
  locale,
}: ProfilePanelProps) {
  const t = useTranslations('profile');

  const headingId = `profile-panel-${panel}`;

  return (
    <section
      aria-labelledby={headingId}
      data-testid="profile-panel"
      data-panel={panel}
      className="space-y-4"
    >
      {/*
        A panel is a section of the profile, so it says which one it is and what
        it holds. Without a visible heading a list of shows sits under four
        unrelated buttons and the reader has to remember which figure they
        pressed; without a subtitle "Artists" could mean the artists someone
        follows or the ones they have actually paid to watch.
      */}
      <SectionHeader
        id={headingId}
        title={t(`panel.${panel}`)}
        subtitle={t(`panelSubtitle.${panel}`)}
      />

      {panel === 'followers' || panel === 'following' ? (
        <Connections
          username={username}
          direction={panel}
          locale={locale}
        />
      ) : panel === 'events' ? (
        <ShowsPanel username={username} locale={locale} />
      ) : panel === 'artists' ? (
        <ArtistsSeenPanel username={username} locale={locale} />
      ) : (
        <ConcertPanel
          panel={panel}
          username={username}
          locale={locale}
        />
      )}
    </section>
  );
}

interface Connection {
  id: string;
  username: string;
  full_name?: string | null;
  avatar_url?: string | null;
}

function Connections({
  username,
  direction,
  locale,
}: {
  username: string;
  direction: 'followers' | 'following';
  locale: Locale;
}) {
  const t = useTranslations('profile');

  const [entries, setEntries] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);

      try {
        const data = await userAPI.getConnections(username, direction);

        if (!cancelled) {
          setEntries(data.users ?? []);
        }
      } catch {
        if (!cancelled) {
          setEntries([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [username, direction]);

  if (loading) {
    return (
      <p className="text-sm text-muted">
        {t('loadingConnections')}
      </p>
    );
  }

  if (entries.length === 0) {
    return (
      <EmptyState
        title={
          direction === 'followers'
            ? t('noFollowers')
            : t('noFollowing')
        }
      />
    );
  }

  return (
    <ul
      className="grid grid-cols-1 gap-2 sm:grid-cols-2"
      data-testid={`profile-${direction}`}
    >
      {entries.map((entry) => (
        <li key={entry.id}>
          <Link
            href={`/${locale}/profile/${entry.username}`}
            data-testid="profile-connection-link"
            className="
              flex
              min-h-[56px]
              items-center
              gap-3
              rounded-lg
              border
              border-border
              bg-card-bg
              px-3
              py-2
              transition-colors
              hover:bg-card-hover
              focus-visible:outline-none
              focus-visible:ring-2
              focus-visible:ring-accent
            "
          >
            <Avatar
              src={entry.avatar_url ?? undefined}
              alt={entry.username}
              fallback={entry.username.charAt(0).toUpperCase()}
              size="md"
            />

            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold text-foreground">
                @{entry.username}
              </span>

              {entry.full_name && (
                <span className="block truncate text-xs text-muted">
                  {entry.full_name}
                </span>
              )}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function ConcertPanel({
  panel,
  username,
  locale,
}: {
  panel: 'reviews' | 'festivals';
  username: string;
  locale: Locale;
}) {
  const [reviews, setReviews] = useState<ProfileReview[]>([]);
  const [festivals, setFestivals] = useState<ProfileFestival[]>([]);
  const [loading, setLoading] = useState(true);

  // One request per panel, scoped to the panel and the profile it was opened
  // for, so switching panels cannot show one list under another's heading.
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);

      try {
        if (panel === 'reviews') {
          const data = await userAPI.getProfileReviews(username, PREVIEW_LIMIT);

          if (!cancelled) {
            setReviews(data.reviews ?? []);
          }
        } else {
          const data = await userAPI.getProfileFestivals(username);

          if (!cancelled) {
            setFestivals(data.festivals ?? []);
          }
        }
      } catch {
        // A list that could not be loaded is reported as empty rather than
        // leaving a spinner on screen forever.
        if (!cancelled) {
          setReviews([]);
          setFestivals([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [panel, username]);

  const t = useTranslations('profile');

  if (loading) {
    return <LoadingState message={t('loading')} />;
  }

  /*
    Each panel always renders its own list container, even when it is empty, and
    puts the empty state inside it. A figure that opens nothing identifiable
    cannot be told apart from a figure that failed to load its rows.
  */

  if (panel === 'reviews') {
    return (
      <div
        className="space-y-4"
        data-testid="profile-reviews"
      >
        {reviews.length === 0 ? (
          <EmptyState
            icon="✍"
            title={t('noReviews')}
            description={t('noReviewsHint')}
          />
        ) : (
          reviews.map((review) => (
            <ReviewCard
              key={`${review.event_id}-${review.reviewed_at ?? ''}`}
              review={review}
              locale={locale}
            />
          ))
        )}
      </div>
    );
  }

  if (panel === 'festivals') {
    return (
      <ul
        className="grid grid-cols-1 gap-3 sm:grid-cols-2"
        data-testid="profile-festivals"
      >
        {festivals.length === 0 ? (
          <li className="sm:col-span-2">
            <EmptyState
              icon="🎪"
              title={t('noFestivals')}
              description={t('noFestivalsHint')}
            />
          </li>
        ) : (
          festivals.map((festival) => (
            <li key={festival.key}>
              <Card
                className="h-full"
                data-testid="profile-festival"
              >
                <p className="break-anywhere font-semibold text-foreground">
                  {/*
                    A festival is only reachable through one of its editions,
                    so the row links to the newest show the person logged
                    rather than to a listing that does not exist.
                  */}
                  {festival.event_id ? (
                    <Link
                      href={`/${locale}/festivals/${festival.event_id}`}
                      data-testid="profile-festival-link"
                      className="
                        block
                        rounded
                        transition-colors
                        hover:text-accent-text
                        focus-visible:outline-none
                        focus-visible:ring-2
                        focus-visible:ring-accent
                      "
                    >
                      {festival.name}
                    </Link>
                  ) : (
                    festival.name
                  )}
                </p>

                <p className="mt-1 text-sm text-muted-subtle">
                  {festival.first_date
                    ? formatEventSchedule(
                        { starts_at: festival.first_date },
                        locale,
                        t('dateUnknown')
                      )
                    : t('dateUnknown')}
                </p>

                <p className="mt-2 text-xs text-muted">
                  {t('festivalCounts', {
                    editions: festival.editions_count,
                    shows: festival.shows_count,
                  })}
                </p>
              </Card>
            </li>
          ))
        )}
      </ul>
    );
  }

  /*
    The artists panel is not a followed-artists list any more, so it has its own
    component rather than being squeezed into this one.
  */
  return null;
}

/**
 * Artists I have seen.
 *
 * This is a record of shows attended, not a list of people pressed Follow on.
 * Two consequences run through the whole component:
 *
 * * an artist only appears if the person has been to a show where they
 *   performed, so following alone never puts them here
 * * the only figure on a row is how many distinct shows that was, because a
 *   follower count beside "3 shows" invites reading the history as popularity
 *
 * A row links to the artist's own page. It does not offer the community as a
 * second destination: the community is a different place, reached from the
 * artist's page, and a history of nights out is not a list of conversations.
 */
function ArtistsSeenPanel({
  username,
  locale,
}: {
  username: string;
  locale: Locale;
}) {
  const t = useTranslations('profile');

  const [artists, setArtists] = useState<ProfileSeenArtist[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);

      try {
        // One request carries every artist and every count. Asking per artist
        // would make the cost of a profile grow with the length of its history.
        const data = await userAPI.getProfileArtistsSeen(username);

        if (!cancelled) {
          setArtists(data.artists ?? []);
          setTotal(data.total ?? 0);
        }
      } catch {
        if (!cancelled) {
          setArtists([]);
          setTotal(0);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [username]);

  if (loading) {
    return <LoadingState message={t('loading')} />;
  }

  return (
    <div className="space-y-3">
      <ul
        className="space-y-2"
        data-testid="profile-artists-seen"
      >
        {artists.length === 0 ? (
          <li>
            <EmptyState
              icon="♪"
              title={t('noArtistsSeen')}
              description={t('noArtistsSeenHint')}
            />
          </li>
        ) : (
          artists.map((artist) => (
            <li key={artist.slug}>
              <SeenArtistRow artist={artist} locale={locale} />
            </li>
          ))
        )}
      </ul>

      {artists.length > 0 && artists.length < total && (
        <p
          className="text-xs text-muted-subtle"
          data-testid="profile-artists-seen-more"
        >
          {t('showsMore', {
            shown: artists.length,
            total,
          })}
        </p>
      )}
    </div>
  );
}

/**
 * One artist the person has seen.
 *
 * An artist with no imported page is rendered as plain text rather than a link.
 * Building a route for a page that does not exist would turn a real attendance
 * into a dead link, and the name is what the person remembers anyway.
 */
function SeenArtistRow({
  artist,
  locale,
}: {
  artist: ProfileSeenArtist;
  locale: Locale;
}) {
  const t = useTranslations('profile');

  const shows = (
    <span className="flex min-w-0 flex-1 items-center gap-3">
      <Avatar
        src={artist.image ?? undefined}
        alt={artist.name}
        fallback="♪"
        size="md"
      />

      <span className="min-w-0 flex-1">
        <span className="block truncate font-semibold text-foreground">
          {artist.name}
        </span>
      </span>

      <span
        className="shrink-0 whitespace-nowrap text-sm text-muted"
        data-testid="profile-artist-shows"
      >
        {t('seenShows', { count: artist.shows_count })}
      </span>
    </span>
  );

  const shell = `
    flex min-h-[64px] items-center rounded-lg border border-border
    bg-card-bg px-3 py-2
  `;

  if (!artist.resolved) {
    return (
      <span
        className={`${shell} cursor-default`}
        data-testid="profile-artist-unresolved"
      >
        {shows}
      </span>
    );
  }

  return (
    <Link
      href={`/${locale}/artists/${artist.slug}`}
      data-testid="profile-artist-page-link"
      className={`
        ${shell}
        transition-colors
        hover:bg-card-hover
        focus-visible:outline-none
        focus-visible:ring-2
        focus-visible:ring-accent
      `}
    >
      {shows}
    </Link>
  );
}

/**
 * Shows, broken down into the three states a show can be in.
 *
 * This is one section, not three: the same list endpoint serves all three, and
 * it answers with the count for every state alongside the rows for the one that
 * was asked for. So the breakdown and the list under it can never disagree, and
 * opening a second state costs one request rather than three.
 *
 * Attended is the state a profile opens on, because it is the one a person
 * comes to a profile to see.
 */
const SHOW_STATES: ProfileShowStatus[] = [
  'attended',
  'want-to-go',
  'maybe',
];

/** What one request answered, tagged with the state it was asked for. */
interface LoadedShows {
  state: ProfileShowStatus;
  events: ProfileEvent[];
  counts: ProfileShowCounts;
  total: number;
}

function ShowsPanel({
  username,
  locale,
}: {
  username: string;
  locale: Locale;
}) {
  const t = useTranslations('profile');

  const [state, setState] = useState<ProfileShowStatus>('attended');
  const [loaded, setLoaded] = useState<LoadedShows | null>(null);
  const [loading, setLoading] = useState(true);

  /*
    The diary is read by scrolling into the past, so the next batch is fetched by
    cursor rather than by page number. `cursor` is whatever the server last sent and
    is passed straight back; the client never reads it.
  */
  const [cursor, setCursor] = useState<ProfileEventCursor | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  /*
    Which calendar day the reader has chosen. Kept here so the calendar and the
    list agree on it, and so switching state clears it rather than leaving a filter
    pointing at a day that is no longer on screen.
  */
  const [focusDay, setFocusDay] = useState<string | null>(null);

  /*
    The years this profile has shows in, fetched once and handed to the calendar.

    Read here rather than inside the calendar because the panel is what knows the
    username's history and because the same figures let the trigger label say
    which month is open without the calendar needing a request per month just to
    know whether to offer a dot.
  */
  const [yearsWithShows, setYearsWithShows] = useState<
    { year: number; shows: number }[]
  >([]);

  useEffect(() => {
    let cancelled = false;

    async function loadYears() {
      try {
        const data = await userAPI.getProfileShowYears(username);

        if (!cancelled) {
          setYearsWithShows(data.years ?? []);
        }
      } catch {
        // A calendar that cannot read the years still opens on this month; it
        // just offers only this year in the selector.
        if (!cancelled) {
          setYearsWithShows([]);
        }
      }
    }

    loadYears();

    return () => {
      cancelled = true;
    };
  }, [username]);

  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) {
      return;
    }

    setLoadingMore(true);

    try {
      const data = await userAPI.getProfileEventsPage(
        username,
        {
          status: state,
          limit: PAGE_SIZE,
          before: cursor.date,
          beforeId: cursor.id,
        }
      );

      setLoaded((current) => {
        if (!current || current.state !== state) {
          // The state changed while the batch was in flight, so this answer
          // belongs to a list that is no longer on screen.
          return current;
        }

        const known = new Set(
          current.events.map((event) => event.event_id)
        );

        /*
          Merged by identity rather than appended. Two batches can overlap if a
          show is logged between two reads, and a duplicated row in a diary reads
          as the reader having been there twice.
        */
        const merged = [
          ...current.events,
          ...(data.events ?? []).filter(
            (event) => !known.has(event.event_id)
          ),
        ];

        return {
          ...current,
          events: merged,
          total: data.total ?? current.total,
        };
      });

      setCursor(data.next_cursor ?? null);
    } catch {
      // A batch that could not be loaded leaves the cursor where it was, so
      // trying again asks for the same rows rather than skipping them.
    } finally {
      setLoadingMore(false);
    }
  }, [cursor, loadingMore, state, username]);

  // Scoped to the profile and the state, so switching state cannot leave one
  // list on screen under another's heading.
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setFocusDay(null);

      try {
        const data = await userAPI.getProfileEventsPage(
          username,
          { status: state, limit: PAGE_SIZE }
        );

        if (cancelled) {
          return;
        }

        setLoaded({
          state,
          events: data.events ?? [],
          counts: {
            attended: data.counts?.attended ?? 0,
            'want-to-go': data.counts?.['want-to-go'] ?? 0,
            maybe: data.counts?.maybe ?? 0,
          },
          total: data.total ?? 0,
        });

        setCursor(data.next_cursor ?? null);
      } catch {
        // A list that could not be loaded is reported as empty rather than
        // leaving a spinner on screen forever.
        if (!cancelled) {
          setLoaded({
            state,
            events: [],
            counts: { attended: 0, 'want-to-go': 0, maybe: 0 },
            total: 0,
          });

          setCursor(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [state, username]);

  /*
    Nothing is rendered until the answer on screen belongs to the state being
    shown.

    `useEffect` runs after paint, so for one frame after a switch the state has
    already changed while the previous state's rows are still in place. Rendering
    those rows under the new state's heading - or rendering an empty list for a
    state that actually has rows - is a lie about what the profile contains, so
    the list waits for its own answer.
  */
  const ready = !loading && loaded !== null && loaded.state === state;

  const counts: ProfileShowCounts = loaded?.counts ?? {
    attended: 0,
    'want-to-go': 0,
    maybe: 0,
  };

  const events = ready ? loaded.events : [];
  const total = ready ? loaded.total : 0;

  /*
    Clicking a marked calendar day narrows the diary to that night. The filter is
    applied here rather than by re-querying, because the rows are already loaded -
    and because a calendar that changed what it fetched would make the reader wait
    to look at a day they have already loaded.
  */
  const visible = focusDay
    ? events.filter((event) =>
        (event.starts_at ?? '').slice(0, 10) === focusDay
      )
    : events;

  /*
    Infinite scroll, on an observer rather than a scroll handler.

    A diary has no natural end to stop at, and a person reading one scrolls to
    find a year rather than to reach a button. An observer on a sentinel at the
    bottom of the list is the honest expression of that: the next batch is
    requested when the reader reaches it, not when they have scrolled past some
    arbitrary distance.

    The button is kept as well, and is what actually loads. A sentinel that
    silently loads pages cannot be triggered without a pointer, cannot be
    reached by a keyboard, and gives a screen-reader user nothing at all - so the
    button stays visible and focusable, and the observer is an addition to it
    rather than a replacement.
  */
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sentinel = sentinelRef.current;

    if (!sentinel || !cursor || loadingMore || loading) {
      return;
    }

    if (typeof IntersectionObserver === 'undefined') {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          loadMore();
        }
      },
      { rootMargin: '400px 0px' }
    );

    observer.observe(sentinel);

    return () => observer.disconnect();
  }, [cursor, loadMore, loading, loadingMore, ready]);

  return (
    <div className="space-y-4">
      {/*
        The counts are on the control itself rather than in a separate summary,
        so the figure a reader taps is the figure they land on.
      */}
      <div
        role="tablist"
        aria-label={t('showsBreakdown')}
        data-testid="profile-shows-breakdown"
        className="
          grid
          grid-cols-3
          gap-1
          rounded-lg
          border
          border-border
          bg-card-bg
          p-1
        "
      >
        {SHOW_STATES.map((item) => {
          const active = state === item;

          return (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setState(item)}
              data-testid={`profile-shows-${item}`}
              className={`
                flex
                min-h-[56px]
                flex-col
                items-center
                justify-center
                gap-1
                rounded-md
                px-2
                py-2
                text-center
                transition-colors
                focus-visible:outline-none
                focus-visible:ring-2
                focus-visible:ring-accent
                ${
                  active
                    ? 'bg-accent-solid text-white'
                    : 'text-muted hover:bg-card-hover hover:text-foreground'
                }
              `}
            >
              <span className="text-lg font-bold leading-none">
                {counts[item]}
              </span>

              <span className="text-xs leading-tight">
                {t(`shows.${item}`)}
              </span>
            </button>
          );
        })}
      </div>

      {/*
        The list container only exists once the rows do. Rendering the spinner
        inside it would mean a caller that waits for the container could still
        be looking at a loading state, which is the one thing it cannot tell from
        a real, shorter list.
      */}
      {!ready ? (
        <LoadingState message={t('loading')} />
      ) : (
        /*
          One wrapper for all three states, and it says which state it is
          holding. Attended renders a calendar page while the other two render
          ordinary lists, so without a shared wrapper a caller could not tell a
          state that is loading from one that is empty, or read which rows
          belong to which state.
        */
        <div
          data-testid="profile-events"
          data-show-state={state}
          data-show-layout={
            state === 'attended' && events.length > 0 ? 'diary' : 'list'
          }
          data-focused-day={focusDay ?? ''}
        >
          {state === 'attended' && events.length > 0 && (
            <ShowCalendar
              username={username}
              focusDay={focusDay}
              onFocusDay={setFocusDay}
              yearsWithShows={yearsWithShows}
            />
          )}

          {events.length === 0 ? (
            <EmptyState
              icon="🎤"
              title={t(`shows.empty.${state}`)}
              description={t(`shows.emptyHint.${state}`)}
            />
          ) : visible.length === 0 ? (
            /*
              The reader chose a day, and no loaded row falls on it. Stated rather
              than shown as an empty list, which would read as somebody who has
              never been anywhere.
            */
            <EmptyState
              icon="📅"
              title={t('calendar.noShowsThatDay')}
              description={t('calendar.clearFilterHint')}
            />
          ) : state === 'attended' ? (
            /*
              Attended shows are read as a diary, so they get a calendar page
              grouped by year and month. Want to go and Maybe stay ordinary
              lists: they are plans rather than a history, and a diary layout
              would overstate how settled they are.
            */
            <AttendedDiary events={visible} locale={locale} />
          ) : (
            <ul className="space-y-3">
              {visible.map((event) => (
                <li key={event.event_id}>
                  <EventRow
                    event={event}
                    locale={locale}
                    state={state}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/*
        More history, offered as a control as well as being fetched on approach.

        The control is not redundant: it is the only way to load the next page
        with a keyboard or without scrolling, and it is what a test drives. It
        appears only while the server still has a next page, so it cannot lead to
        rows already on screen, and it is not a dead control at the end of a list.
      */}
      {ready && cursor && (
        <>
          {/*
            Watched, not rendered as anything. It exists purely so the observer
            has a node to watch at the point the reader has reached the end of
            what is loaded.
          */}
          <div
            ref={sentinelRef}
            aria-hidden="true"
            data-testid="profile-shows-sentinel"
          />

          <button
            type="button"
            onClick={loadMore}
            disabled={loadingMore}
            className="w-full rounded-lg border border-hairline-strong bg-surface-raised/60 px-4 py-3 text-sm text-muted transition hover:bg-surface-raised hover:text-foreground disabled:opacity-60 focus-ring"
            data-testid="profile-shows-load-more"
          >
            {loadingMore ? t('showsLoadingMore') : t('showsLoadMore')}
          </button>
        </>
      )}

      {ready && !cursor && events.length > 0 && (
        <p
          className="text-xs text-muted-subtle"
          data-testid="profile-shows-more"
        >
          {t('showsMore', {
            shown: events.length,
            total,
          })}
        </p>
      )}
    </div>
  );
}

/**
 * A show placed on a calendar page.
 *
 * A concert history is read as a diary, so the list is grouped by the year and
 * month the show happened in and each row leads with its day number. Grouping is
 * done here rather than on the server because it is a way of *reading* one list,
 * not another query: the same rows, arranged as a calendar.
 *
 * `starts_at` is the only field used. Sorting by when a row was written would
 * order the diary by typing speed rather than by when the night happened.
 */
interface DiaryMonth {
  /** `YYYY-MM`, which sorts correctly as a plain string. */
  key: string;

  year: string;

  month: string;

  events: ProfileEvent[];
}

interface DiaryYear {
  key: string;

  year: string;

  months: DiaryMonth[];
}

/** Shows a person attended, grouped into years and months, newest first. */
function buildDiary(events: ProfileEvent[]): DiaryYear[] {
  const dated = events.filter((event) => Boolean(event.starts_at));

  // A show without a date still happened, so it is kept and grouped under an
  // undated heading rather than dropped from someone's history.
  const undated = events.filter((event) => !event.starts_at);

  const years = new Map<string, Map<string, ProfileEvent[]>>();

  for (const event of dated) {
    const when = new Date(event.starts_at as string);

    if (Number.isNaN(when.getTime())) {
      continue;
    }

    const year = String(when.getFullYear());
    const month = String(when.getMonth() + 1).padStart(2, '0');

    const months = years.get(year) ?? new Map<string, ProfileEvent[]>();

    months.set(month, [...(months.get(month) ?? []), event]);

    years.set(year, months);
  }

  /*
    `Array.from` rather than spreading a Map iterator: this project compiles to
    a target below es2015, where an iterator is not itself iterable.
  */
  const byYear = Array.from(years.entries())
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([year, months]) => ({
      key: year,
      year,
      months: Array.from(months.entries())
        .sort(([a], [b]) => b.localeCompare(a))
        .map(([key, rows]) => ({
          key: `${year}-${key}`,
          year,
          month: key,
          // Newest night first inside the month too, so the page reads
          // consistently from top to bottom.
          events: rows.slice().sort(
            (a, b) =>
              new Date(b.starts_at as string).getTime() -
              new Date(a.starts_at as string).getTime()
          ),
        })),
    }));

  if (undated.length === 0) {
    return byYear;
  }

  return byYear.concat([
    {
      key: 'undated',
      year: '',
      months: [
        {
          key: 'undated',
          year: '',
          month: '',
          events: undated,
        },
      ],
    },
  ]);
}

/** The month a group of shows happened in, named in the reader's language. */
function monthLabel(
  year: string,
  month: string,
  locale: Locale,
): string {
  if (!year || !month) {
    return '';
  }

  /*
    Built from the group rather than from whichever row happened to be first, so
    the heading is the month the rows are grouped under.
  */
  const when = new Date(Number(year), Number(month) - 1, 1);

  if (Number.isNaN(when.getTime())) {
    return '';
  }

  return new Intl.DateTimeFormat(intlTag(locale), {
    month: 'long',
  }).format(when);
}

/**
 * The day column: a single day, or the real span of a multi-day event.
 *
 * A festival date runs from one evening to the small hours, so `04-06` is what
 * the row shows rather than a single number that would understate it. The span
 * is read from the event's own `ends_at`; nothing is invented, and an event with
 * no end date simply shows its start day.
 */
function dayRangeLabel(event: ProfileEvent): string | null {
  const start = event.starts_at ? new Date(event.starts_at) : null;

  if (!start || Number.isNaN(start.getTime())) {
    return null;
  }

  const from = String(start.getDate()).padStart(2, '0');

  if (!event.ends_at) {
    return from;
  }

  const end = new Date(event.ends_at);

  if (Number.isNaN(end.getTime())) {
    return from;
  }

  const to = String(end.getDate()).padStart(2, '0');

  // The same day, or an end that precedes the start, means there is no span to
  // show. Both are printed as the single day they really are.
  if (to === from || end.getTime() < start.getTime()) {
    return from;
  }

  return `${from}–${to}`;
}

function DiaryRow({
  event,
  locale,
}: {
  event: ProfileEvent;
  locale: Locale;
}) {
  const t = useTranslations('profile');

  const day = dayRangeLabel(event);

  const place = [event.venue_name, event.city].filter(Boolean).join(' · ');

  const artists = event.artist_names.filter(Boolean).join(', ');

  return (
    <Link
      href={`/${locale}/events/${event.event_id}`}
      data-testid="profile-event-link"
      data-diary-day={day ?? undefined}
      data-has-review={event.has_review ? 'true' : undefined}
      className="
        group
        relative
        grid
        grid-cols-[3.25rem_1fr]
        gap-x-3
        rounded-md
        py-2
        pl-4
        pr-1
        transition-colors
        hover:bg-card-hover
        focus-visible:outline-none
        focus-visible:ring-2
        focus-visible:ring-accent
      "
    >
      {/*
        The spine. It runs down the left of the day column so a month reads as one
        continuous run of nights rather than a stack of separate cards, and it is
        hidden on each month's first row so the timeline has a beginning.

        It is a hairline, not a rule: the day numbers are the structure, and this
        only has to say "these belong together".
      */}
      <span
        aria-hidden="true"
        className="
          pointer-events-none
          absolute
          left-1
          top-0
          h-full
          w-px
          bg-border-strong
          group-first:hidden
        "
      />

      <span
        className="
          relative
          text-[26px]
          font-bold
          leading-none
          tracking-tight
          tabular-nums
          text-accent-text
          sm:text-[30px]
        "
        data-testid="profile-diary-day"
      >
        {day ?? '--'}
      </span>

      <span className="min-w-0">
        <span className="flex items-baseline gap-2">
          <span
            className="
              min-w-0
              flex-1
              truncate
              font-semibold
              text-foreground
            "
            data-testid="profile-diary-title"
          >
            {event.title}
          </span>

          {/*
            A rating beside a show means the person wrote about it, which is a
            different kind of memory from having attended it. It is a marker, not
            a score to display.
          */}
          {event.has_review && (
            <span
              className="
                shrink-0
                text-xs
                font-medium
                text-accent-text
              "
              data-testid="profile-diary-review"
              title={t('reviewedBadge')}
            >
              <span aria-hidden="true">★</span>
              {typeof event.rating === 'number' && (
                <span className="ml-1 tabular-nums">{event.rating}</span>
              )}
              <span className="sr-only">{t('reviewedBadge')}</span>
            </span>
          )}
        </span>

        {place && (
          <span
            className="mt-0.5 block truncate text-sm text-muted"
            data-testid="profile-diary-place"
          >
            {place}
          </span>
        )}

        {/*
          The bill, when it is not already the title. On a festival date the
          title is an edition ("Day 1"), so the festival name is what makes the
          row readable.
        */}
        {(event.festival || artists) && (
          <span className="mt-1 flex flex-wrap items-center gap-1.5">
            {event.festival && (
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
                data-testid="profile-diary-festival"
              >
                {event.festival.name}
              </span>
            )}

            {artists && (
              <span
                className="
                  min-w-0
                  truncate
                  text-xs
                  text-muted-subtle
                "
                data-testid="profile-diary-artists"
              >
                {artists}
              </span>
            )}
          </span>
        )}
      </span>
    </Link>
  );
}

/** The attended shows, laid out as a diary page. */
function AttendedDiary({
  events,
  locale,
}: {
  events: ProfileEvent[];
  locale: Locale;
}) {
  const t = useTranslations('profile');

  const years = buildDiary(events);

  return (
    <div
      className="space-y-6"
      data-testid="profile-diary"
    >
      {years.map((year) => (
        <section
          key={year.key}
          aria-label={year.year || t('dateUnknown')}
          data-testid="profile-diary-year"
          data-year={year.year}
        >
          {/*
            The year is a rule with a figure on it rather than a heading: it
            divides the page without competing with the section header above it.
          */}
          {year.year && (
            <h3
              className="
                mb-2
                flex
                items-center
                gap-3
                text-sm
                font-bold
                tracking-[0.2em]
                text-muted-subtle
              "
            >
              {year.year}

              <span
                aria-hidden="true"
                className="h-px flex-1 bg-border"
              />
            </h3>
          )}

          {year.months.map((month) => (
            <div
              key={month.key}
              className="mb-4 last:mb-0"
              data-testid="profile-diary-month"
              /*
                `YYYYMM`, which sorts correctly as a plain string and matches
                the endpoint's own `starts_at` once the separators are dropped.
              */
              data-month={`${month.year}${month.month}`}
            >
              {month.month && (
                <h4
                  className="
                    mb-1
                    px-2
                    text-xs
                    font-semibold
                    uppercase
                    tracking-[0.18em]
                    text-muted
                  "
                  data-testid="profile-diary-month-label"
                >
                  {monthLabel(month.year, month.month, locale)}
                </h4>
              )}

              <ul className="space-y-0.5">
                {month.events.map((event) => (
                  <li key={event.event_id}>
                    <DiaryRow event={event} locale={locale} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}

/**
 * One show from a plan rather than a memory: Want to Go or Maybe.
 *
 * This is deliberately not the diary row. An attended show is history and is
 * read as an archive; a planned show is a decision that has not happened yet,
 * so it leads with when it is and reads as something still to be acted on. The
 * two states also differ from each other: Want to Go is a plan, Maybe is an
 * open question, and a reader should be able to tell them apart without reading
 * the tab they are on.
 */
function EventRow({
  event,
  locale,
  state,
}: {
  event: ProfileEvent;
  locale: Locale;
  state: ProfileShowStatus;
}) {
  const t = useTranslations('profile');

  const artists = event.artist_names.filter(Boolean).join(', ');

  const place = [event.venue_name, event.city].filter(Boolean).join(' · ');

  const tentative = state === 'maybe';

  return (
    <Link
      href={`/${locale}/events/${event.event_id}`}
      data-testid="profile-event-link"
      data-show-state={state}
      className={`
        flex min-h-[64px] flex-col justify-center rounded-lg border
        bg-card-bg px-4 py-3 transition-colors hover:bg-card-hover
        focus-visible:outline-none focus-visible:ring-2
        focus-visible:ring-accent
        ${
          tentative
            ? 'border-dashed border-border'
            : 'border-border'
        }
      `}
    >
      <span className="flex items-baseline justify-between gap-2">
        <span className="truncate font-semibold text-foreground">
          {event.title}
        </span>

        {/*
          The state is repeated on the row. Someone scrolling a list of a dozen
          shows should not have to remember which tab they are on to know
          whether they decided or not.
        */}
        <span
          className={`
            shrink-0 whitespace-nowrap text-xs font-medium
            ${tentative ? 'text-muted-subtle' : 'text-accent-text'}
          `}
          data-testid="profile-plan-state"
        >
          {t(`shows.${state}`)}
        </span>
      </span>

      <span className="mt-1 truncate text-sm text-muted">
        {[
          formatEventSchedule(event, locale, t('dateUnknown')),
          artists,
          place,
        ]
          .filter(Boolean)
          .join(' · ')}
      </span>

      {event.festival && (
        <span
          className="mt-1 inline-block rounded border border-accent/40 px-1.5 py-px text-[11px] font-medium uppercase tracking-wide text-accent-text"
          data-testid="profile-diary-festival"
        >
          {event.festival.name}
        </span>
      )}
    </Link>
  );
}