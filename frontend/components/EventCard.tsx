'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTranslations } from 'next-intl';

import Card from './ui/Card';
import Badge from './ui/Badge';

import { resolveLocale, formatDateSpan, formatEventTime } from '@/app/lib/dates';

/**
 * Read the locale from the current URL so every event link keeps the reader
 * in the language they are browsing with.
 */
function useResolvedLocale() {
  const pathname = usePathname() || '';
  const segment = pathname.split('/')[1];

  return resolveLocale(segment);
}


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
  event: EventCardProps['event'],
  locale: ReturnType<typeof resolveLocale>,
) {
  return formatDateSpan(
    event.starts_at,
    isFestival(event)
      ? event.ends_at
      : null,
    locale,
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

  const locale =
    useResolvedLocale();

  const t =
    useTranslations('eventCard');

  const formattedDate =
    formatEventDate(event, locale);

  // A festival spans days, so it carries no single start time.
  const formattedTime =
    festival
      ? null
      : formatEventTime(
          event.starts_at,
          locale
        );

  const venueName =
    getVenueName(event);

  const city =
    getCity(event);

  const country =
    getCountry(event);


  return (

    <Link
      href={`/${locale}/events/${event.id}`}
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
                ? t('festival')
                : t('concert')
              }

            </Badge>

          </div>


          <div className="
            text-sm
            text-muted
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
                text-muted-subtle
              ">

                {t('tracking', {
                  count:
                    event.festival
                      .tracking_count,
                })}

              </p>

            )
          }


          <div className="
            mt-auto
            pt-5
            flex
            gap-3
            text-xs
            text-muted
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