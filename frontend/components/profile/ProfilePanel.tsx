'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';

import { userAPI } from '@/app/lib/api';
import {
  formatEventSchedule,
  byNameInLocale,
} from '@/app/lib/dates';
import type { Locale } from '@/app/i18n';
import type {
  ProfileArtist,
  ProfileEvent,
  ProfileFestival,
  ProfileReview,
} from '@/app/types/profile';
import ReviewCard from '@/components/ReviewCard';

import Avatar from '@/components/ui/Avatar';
import Card from '@/components/ui/Card';
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

  return (
    <section
      aria-label={t('listsFor', { what: t(`panel.${panel}`) })}
      data-testid="profile-panel"
      data-panel={panel}
      className="space-y-4"
    >
      {panel === 'followers' || panel === 'following' ? (
        <Connections
          username={username}
          direction={panel}
          locale={locale}
        />
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
  panel: 'reviews' | 'events' | 'festivals' | 'artists';
  username: string;
  locale: Locale;
}) {
  const [reviews, setReviews] = useState<ProfileReview[]>([]);
  const [events, setEvents] = useState<ProfileEvent[]>([]);
  const [festivals, setFestivals] = useState<ProfileFestival[]>([]);
  const [artists, setArtists] = useState<ProfileArtist[]>([]);
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
        } else if (panel === 'events') {
          const data = await userAPI.getProfileEvents(username, PREVIEW_LIMIT);

          if (!cancelled) {
            setEvents(data.events ?? []);
          }
        } else if (panel === 'festivals') {
          const data = await userAPI.getProfileFestivals(username);

          if (!cancelled) {
            setFestivals(data.festivals ?? []);
          }
        } else {
          const data = await userAPI.getProfileArtists(username, PREVIEW_LIMIT);

          if (!cancelled) {
            setArtists(data.artists ?? []);
          }
        }
      } catch {
        // A list that could not be loaded is reported as empty rather than
        // leaving a spinner on screen forever.
        if (!cancelled) {
          setReviews([]);
          setEvents([]);
          setFestivals([]);
          setArtists([]);
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

  if (panel === 'events') {
    return (
      <ul
        className="space-y-3"
        data-testid="profile-events"
      >
        {events.length === 0 ? (
          <li>
            <EmptyState
              icon="🎤"
              title={t('noShows')}
              description={t('noShowsHint')}
            />
          </li>
        ) : (
          events.map((event) => (
            <li key={event.event_id}>
              <EventRow event={event} locale={locale} />
            </li>
          ))
        )}
      </ul>
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
    Each followed artist links to that artist's community, because following an
    artist is exactly what puts someone in it. The post count comes from the
    same response, so a community with no posts reads as zero rather than blank.
  */
  return (
    <ul
      className="grid grid-cols-1 gap-3 sm:grid-cols-2"
      data-testid="profile-artists"
    >
      {artists.length === 0 ? (
        <li className="sm:col-span-2">
          <EmptyState
            icon="♪"
            title={t('noArtists')}
            description={t('noArtistsHint')}
          />
        </li>
      ) : (
        byNameInLocale(artists, locale).map((artist) => (
          <li key={artist.slug}>
            <Link
              href={`/${locale}/artists/${artist.slug}/community`}
              data-testid="profile-artist-link"
              className="
                flex
                min-h-[64px]
                items-center
                gap-3
                rounded-lg
                border
                border-border
                bg-card-bg
                px-3
                py-3
                transition-colors
                hover:bg-card-hover
                focus-visible:outline-none
                focus-visible:ring-2
                focus-visible:ring-accent
              "
            >
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

                <span className="mt-1 block text-xs text-muted">
                  {t('communityPosts', {
                    count: artist.posts_count,
                  })}
                </span>
              </span>
            </Link>
          </li>
        ))
      )}
    </ul>
  );
}

/** One show from someone's log, linking to the event page. */
function EventRow({
  event,
  locale,
}: {
  event: ProfileEvent;
  locale: Locale;
}) {
  const t = useTranslations('profile');

  const artists = event.artist_names.filter(Boolean).join(', ');
  const place = event.venue_name || event.city;

  return (
    <Link
      href={`/${locale}/events/${event.event_id}`}
      data-testid="profile-event-link"
      className="
        flex
        min-h-[64px]
        flex-col
        justify-center
        rounded-lg
        border
        border-border
        bg-card-bg
        px-4
        py-3
        transition-colors
        hover:bg-card-hover
        focus-visible:outline-none
        focus-visible:ring-2
        focus-visible:ring-accent
      "
    >
      <span className="truncate font-semibold text-foreground">
        {event.title}
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
        <span className="mt-1 block truncate text-xs text-accent-text">
          {t('festivalEntry', { name: event.festival.name })}
        </span>
      )}
    </Link>
  );
}