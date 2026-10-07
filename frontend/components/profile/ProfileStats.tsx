'use client';

import { useTranslations } from 'next-intl';

import type { ProfileStats as ProfileStatsType } from '@/app/types/profile';

/**
 * Which list each figure opens.
 *
 * `null` means the figure has no list behind it: there is nothing to open, and a
 * control that opens nothing is worse than a plain number.
 */
type Panel =
  | 'reviews'
  | 'events'
  | 'festivals'
  | 'artists'
  | 'followers'
  | 'following'
  | null;

interface ProfileStatsProps {
  stats: ProfileStatsType;
  /** Which list is open, if any; tapping the same figure again closes it. */
  panel: Panel;
  onToggle: (panel: Exclude<Panel, null>) => void;
}

export default function ProfileStats({
  stats,
  panel,
  onToggle,
}: ProfileStatsProps) {
  const t = useTranslations('profile');

  /*
    Every figure here is counted on the server from the rows behind it, and
    every one of them leads to those rows.

    "Shows" counts every show the person has logged, across all three states,
    because opening it breaks down into all three. An analytics counter that
    cannot be opened is not something a profile needs, so "upcoming" and
    "posts" stay gone rather than shown as unclickable numbers.

    "Artists" counts the artists they have been to a show of, because that is
    what the list behind it holds. It used to count the artists they follow,
    which meant the figure and the list it opened were about two different
    things: a header number of 3 above a list of everyone they have actually
    seen. Following is still a real thing on a profile, but it belongs to the
    header's followers/following row, where an intention belongs.
  */
  const shows =
    (stats.shows_attended ?? 0) +
    (stats.shows_going ?? 0) +
    (stats.shows_maybe ?? 0);

  const figures = [
    {
      key: 'reviews' as const,
      value: stats.reviews_count ?? 0,
      label: t('statReviews'),
    },
    {
      key: 'events' as const,
      value: shows,
      label: t('statShows'),
    },
    {
      key: 'festivals' as const,
      value: stats.festivals_count ?? 0,
      label: t('statFestivals'),
    },
    {
      key: 'artists' as const,
      value: stats.artists_seen ?? 0,
      label: t('statArtists'),
    },
  ];

  return (
    <div
      className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3"
      data-testid="profile-stats"
    >
      {figures.map((figure) => {
        const open = panel === figure.key;

        return (
          <button
            key={figure.key}
            type="button"
            onClick={() => onToggle(figure.key)}
            aria-pressed={open}
            data-testid={`profile-stat-${figure.key}`}
            className={`
              min-h-[72px]
              rounded-xl
              border
              px-3
              py-3
              text-center
              transition-colors
              focus-visible:outline-none
              focus-visible:ring-2
              focus-visible:ring-accent
              ${
                open
                  ? 'border-accent bg-accent/10'
                  : 'border-border bg-card-bg hover:bg-card-hover'
              }
            `}
          >
            <span
              className={`
                block
                text-2xl
                font-bold
                leading-none
                ${open ? 'text-accent-text' : 'text-foreground'}
              `}
            >
              {figure.value}
            </span>

            <span
              className={`
                mt-1.5
                block
                text-sm
                ${open ? 'text-foreground' : 'text-muted'}
              `}
            >
              {figure.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}