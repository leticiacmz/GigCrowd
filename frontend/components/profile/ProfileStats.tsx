'use client';

import { useTranslations } from 'next-intl';

interface ProfileStatsProps {
  stats: {
    followers_count?: number;
    following_count?: number;

    shows_attended: number;
    shows_going: number;
    shows_maybe: number;

    artists_seen: number;

    upcoming_events: number;

    total_posts: number;
  };
}

export default function ProfileStats({
  stats,
}: ProfileStatsProps) {
  const t = useTranslations('profile');

  // Every value is counted on the server from the rows behind it, and every
  // label is translated so the six figures read the same in all languages.
  const cards = [
    {
      label: t('statShows'),
      value: stats.shows_attended ?? 0,
      testId: 'profile-stat-shows',
    },
    {
      label: t('statGoing'),
      value: stats.shows_going ?? 0,
      testId: 'profile-stat-going',
    },
    {
      label: t('statMaybe'),
      value: stats.shows_maybe ?? 0,
      testId: 'profile-stat-maybe',
    },
    {
      label: t('statArtists'),
      value: stats.artists_seen ?? 0,
      testId: 'profile-stat-artists',
    },
    {
      label: t('statUpcoming'),
      value: stats.upcoming_events ?? 0,
      testId: 'profile-stat-upcoming',
    },
    {
      label: t('statPosts'),
      value: stats.total_posts ?? 0,
      testId: 'profile-stat-posts',
    },
  ];

  return (
    <div
      className="
        grid
        grid-cols-2
        md:grid-cols-3
        gap-4
      "
      data-testid="profile-stats"
    >
      {cards.map((card) => (
        <div
          key={card.testId}
          data-testid={card.testId}
          className="
            bg-card-hover
            border
            border-border
            rounded-lg
            p-5
            text-center
          "
        >
          <div
            className="
              text-3xl
              font-bold
            "
          >
            {card.value}
          </div>

          <div
            className="
              text-muted
              mt-2
            "
          >
            {card.label}
          </div>
        </div>
      ))}
    </div>
  );
}