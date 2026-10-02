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
    every one of them leads to those rows. An analytics counter that cannot be
    opened is not something a profile needs, so "shows", "going", "maybe",
    "upcoming" and "posts" are gone rather than shown as unclickable numbers.
  */
  const figures = [
    {
      key: 'reviews' as const,
      value: stats.reviews_count ?? 0,
      label: t('statReviews'),
    },
    {
      key: 'events' as const,
      value: stats.shows_attended ?? 0,
      label: t('statShows'),
    },
    {
      key: 'festivals' as const,
      value: stats.festivals_count ?? 0,
      label: t('statFestivals'),
    },
    {
      key: 'artists' as const,
      value: stats.followed_artists_count ?? 0,
      label: t('statArtists'),
    },
  ];

  return (
    <div
      className="grid grid-cols-2 gap-3 sm:grid-cols-4"
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
            className="
              min-h-[64px]
              rounded-lg
              border
              border-border
              bg-card-bg
              px-3
              py-3
              text-center
              transition-colors
              hover:bg-card-hover
              focus-visible:outline-none
              focus-visible:ring-2
              focus-visible:ring-accent
            "
          >
            <span
              className="
                block
                text-2xl
                font-bold
                text-foreground
              "
            >
              {figure.value}
            </span>

            <span
              className="
                mt-1
                block
                text-sm
                text-muted
              "
            >
              {figure.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}