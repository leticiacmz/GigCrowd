import Link from 'next/link';

import {
  format,
} from 'date-fns';

import Card from './ui/Card';
import Badge from './ui/Badge';


interface EventCardProps {

  event: {

    id: string;

    title: string;

    starts_at: string;

    ends_at?: string | null;

    event_type?: string;

    venue?: {

      name: string;

      city?: string | null;

      country?: string | null;

    } | null;

    venue_slug?: string | null;

    location?: {

      city?: string | null;

      country?: string | null;

      latitude?: number | null;

      longitude?: number | null;

    } | null;

    festival?: {

      series_id?: string | null;

      name?: string | null;

      edition?: string | null;

      url?: string | null;

      tracking_count?: number | null;

    } | null;

    going_count?: number;

    maybe_count?: number;

    went_count?: number;

  };

}


function isFestival(event: EventCardProps['event']) {

  return event.event_type === 'FestivalInstance';

}


function formatEventDate(
  event: EventCardProps['event']
) {

  const startDate =
    new Date(event.starts_at);

  if (
    isFestival(event) &&
    event.ends_at
  ) {

    const endDate =
      new Date(event.ends_at);

    const sameYear =
      startDate.getFullYear() ===
      endDate.getFullYear();

    if (sameYear) {

      return `${format(
        startDate,
        'MMM d'
      )} – ${format(
        endDate,
        'MMM d, yyyy'
      )}`;

    }

    return `${format(
      startDate,
      'MMM d, yyyy'
    )} – ${format(
      endDate,
      'MMM d, yyyy'
    )}`;

  }

  return format(
    startDate,
    'MMM d, yyyy'
  );

}


function formatEventTime(
  event: EventCardProps['event']
) {

  if (isFestival(event)) {
    return null;
  }

  return format(
    new Date(event.starts_at),
    'h:mm a'
  );

}


function getVenueName(
  event: EventCardProps['event']
) {

  if (event.venue?.name) {
    return event.venue.name;
  }

  if (event.venue_slug) {
    return event.venue_slug
      .replace(/-/g, ' ');
  }

  return null;

}


function getCity(
  event: EventCardProps['event']
) {

  return (
    event.location?.city ??
    event.venue?.city ??
    null
  );

}


function getCountry(
  event: EventCardProps['event']
) {

  return (
    event.location?.country ??
    event.venue?.country ??
    null
  );

}


export default function EventCard({
  event,
}: EventCardProps) {

  const festival =
    isFestival(event);

  const formattedDate =
    formatEventDate(event);

  const formattedTime =
    formatEventTime(event);

  const venueName =
    getVenueName(event);

  const city =
    getCity(event);

  const country =
    getCountry(event);


  return (

    <Link
      href={`/events/${event.id}`}
      className="block h-full"
    >

      <Card
        hoverable
        className="
          h-full
          p-5
          transition
        "
      >

        <div className="
          flex
          flex-col
          h-full
        ">

          <div className="
            flex
            items-start
            justify-between
            gap-3
            mb-4
          ">

            <h3 className="
              font-semibold
              text-lg
              line-clamp-2
            ">

              {
                festival &&
                event.festival?.name
                  ? event.festival.name
                  : event.title
              }

            </h3>

            <Badge
              variant="accent"
              size="sm"
            >

              {festival
                ? 'Festival'
                : 'Concert'
              }

            </Badge>

          </div>


          <div className="
            text-sm
            text-gray-400
            space-y-2
          ">

            <p>
              {formattedDate}
            </p>


            {formattedTime && (

              <p>
                {formattedTime}
              </p>

            )}


            {venueName && (

              <p>
                {venueName}
              </p>

            )}


            {(city || country) && (

              <p>

                {city}

                {city && country && (
                  <>
                    {' • '}
                  </>
                )}

                {country}

              </p>

            )}

          </div>


          {festival &&
            event.festival?.tracking_count != null && (

              <p className="
                mt-4
                text-xs
                text-gray-500
              ">

                {event.festival.tracking_count}
                {' '}
                people tracking this festival

              </p>

            )
          }


          <div className="
            mt-auto
            pt-5
            flex
            gap-3
            text-xs
            text-gray-400
          ">

            <span>
              ✓ {event.going_count ?? 0}
            </span>

            <span>
              ? {event.maybe_count ?? 0}
            </span>

            <span>
              ★ {event.went_count ?? 0}
            </span>

          </div>


        </div>

      </Card>

    </Link>

  );

}