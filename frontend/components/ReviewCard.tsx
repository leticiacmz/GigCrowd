'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';

import Card from './ui/Card';
import ReviewStars from './ReviewStars';
import { formatEventSchedule } from '@/app/lib/dates';
import type { Locale } from '@/app/i18n';
import type { ProfileReview } from '@/app/types/profile';

interface ReviewCardProps {
  review: ProfileReview;
  /** The reader's locale, so the date and every link follow it. */
  locale: Locale;
}

/**
 * One review, as it appears on a profile and on the event it belongs to.
 *
 * The review is the opinion, so it shows whatever of it was written: the
 * rating when the opinion has one, the words when there are any, the photo
 * when there is one. A review written without stars draws no stars rather
 * than an empty row of them, and the stars that are drawn are labelled
 * rather than left as five unlabelled symbols.
 */
export default function ReviewCard({
  review,
  locale,
}: ReviewCardProps) {
  const t = useTranslations('review');
  const tProfile = useTranslations('profile');

  const artistLine = review.artist_names.filter(Boolean).join(', ');
  const place = review.venue_name || review.city;

  return (
    <Card
      className="space-y-4"
      data-testid="review-card"
      data-event-id={review.event_id}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        {typeof review.rating === 'number' ? (
          <ReviewStars rating={review.rating} />
        ) : (
          /*
            Nothing was rated, so nothing is drawn: an empty row of five
            stars would read like a verdict of zero. The empty span keeps
            the date on its side of the card either way.
          */
          <span aria-hidden="true" />
        )}

        <time
          className="text-xs text-muted-subtle"
          dateTime={review.starts_at ?? undefined}
        >
          {formatEventSchedule(review, locale, t('dateUnavailable'))}
        </time>
      </div>

      <div className="min-w-0">
        <Link
          href={`/${locale}/events/${review.event_id}`}
          className="block truncate font-semibold text-foreground transition-colors hover:text-accent-text"
        >
          {review.title}
        </Link>

        {(artistLine || place) && (
          <p className="mt-1 truncate text-sm text-muted">
            {[artistLine, place].filter(Boolean).join(' · ')}
          </p>
        )}
      </div>

      {review.photo_url && (
        <a
          href={review.photo_url}
          target="_blank"
          rel="noopener noreferrer"
          className="block"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={review.photo_url}
            alt={t('photoAlt')}
            data-testid="review-photo"
            loading="lazy"
            className="h-48 w-full rounded-lg border border-border object-cover"
          />
        </a>
      )}

      {review.review && (
        <p
          className="whitespace-pre-line break-anywhere leading-relaxed text-foreground"
          data-testid="review-text"
        >
          {review.review}
        </p>
      )}

      {review.festival && (
        <p className="text-xs text-muted-subtle">
          {tProfile('festivalEntry', {
            name: review.festival.name,
          })}
        </p>
      )}
    </Card>
  );
}