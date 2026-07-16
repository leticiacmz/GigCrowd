interface ProfileStatsProps {

  stats: {

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

      value: stats.shows_attended,

    },

    {

      label: 'Going',

      value: stats.shows_going,

    },

    {

      label: 'Maybe',

      value: stats.shows_maybe,

    },

    {

      label: 'Artists',

      value: stats.artists_seen,

    },

    {

      label: 'Upcoming',

      value: stats.upcoming_events,

    },

    {

      label: 'Posts',

      value: stats.total_posts,

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

      {

        cards.map(

          card => (

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

          )

        )

      }

    </div>

  );

}