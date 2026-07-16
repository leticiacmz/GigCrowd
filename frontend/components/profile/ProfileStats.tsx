'use client';

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
  const cards = [
    {
      label: 'Shows',
      value: stats.shows_attended ?? 0,
    },
    {
      label: 'Going',
      value: stats.shows_going ?? 0,
    },
    {
      label: 'Maybe',
      value: stats.shows_maybe ?? 0,
    },
    {
      label: 'Artists',
      value: stats.artists_seen ?? 0,
    },
    {
      label: 'Upcoming',
      value: stats.upcoming_events ?? 0,
    },
    {
      label: 'Posts',
      value: stats.total_posts ?? 0,
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
    >
      {cards.map((card) => (
        <div
          key={card.label}
          className="
            bg-gray-900
            border
            border-gray-800
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
              text-gray-400
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