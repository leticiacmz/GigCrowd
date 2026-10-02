'use client';

import { useTranslations } from 'next-intl';

/**
 * A rating, read or written.
 *
 * When `onChange` is given the stars are buttons the reader can press; without
 * it the same markup is a read-only figure, so a rating is never drawn two
 * different ways. The stars are labelled for assistive technology in the
 * reader's language, because a row of five symbols says nothing on its own.
 */

interface ReviewStarsProps {
  rating: number;
  onChange?: (rating: number) => void;
  /** Renders larger, for the editor. */
  size?: 'sm' | 'lg';
  className?: string;
  disabled?: boolean;
}

const MAX_STARS = 5;

export default function ReviewStars({
  rating,
  onChange,
  size = 'sm',
  className = '',
  disabled = false,
}: ReviewStarsProps) {
  const t = useTranslations('review');

  const glyphs = Array.from({ length: MAX_STARS }, (_, index) => index + 1);
  const readable = Math.min(MAX_STARS, Math.max(0, Math.round(rating)));
  const label = `${t('ratingLabel', { rating: readable, max: MAX_STARS })}`;

  if (!onChange) {
    return (
      <p
        className={`flex items-center gap-0.5 text-accent-text ${className}`}
        data-testid="review-stars"
        data-rating={readable}
        role="img"
        aria-label={label}
        title={label}
      >
        {glyphs.map((star) => (
          <span key={star} aria-hidden="true">
            {star <= readable ? '★' : '☆'}
          </span>
        ))}
      </p>
    );
  }

  return (
    <div
      className={`flex items-center gap-1 ${className}`}
      role="radiogroup"
      aria-label={t('chooseRating')}
    >
      {glyphs.map((star) => {
        const filled = star <= rating;

        return (
          <button
            key={star}
            type="button"
            role="radio"
            aria-checked={star === rating}
            aria-label={t('rateLabel', { rating: star, max: MAX_STARS })}
            data-testid={`review-star-${star}`}
            disabled={disabled}
            onClick={() => onChange(star)}
            className={`
              inline-flex
              min-h-[32px]
              min-w-[32px]
              items-center
              justify-center
              rounded
              p-0.5
              leading-none
              transition
              focus-visible:outline-none
              focus-visible:ring-2
              focus-visible:ring-accent
              disabled:opacity-50
              ${size === 'lg' ? 'text-3xl' : 'text-lg'}
              ${filled ? 'text-accent-text' : 'text-muted-subtle'}
              ${disabled ? '' : 'hover:scale-110'}
            `}
          >
            <span aria-hidden="true">{filled ? '★' : '☆'}</span>
          </button>
        );
      })}
    </div>
  );
}