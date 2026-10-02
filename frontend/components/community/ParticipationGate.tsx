'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';

import { getLoginPath } from '@/app/lib/auth';
import Button from '@/components/ui/Button';
import type { ParticipationLevel } from '@/app/types/community';

interface ParticipationGateProps {
  level: ParticipationLevel;
  artistName: string;
  artistSlug: string;
  locale: string;
  followLoading: boolean;
  onFollow: () => void;
}

/**
 * Explains why a visitor cannot post or comment yet.
 *
 * The two read-only cases get deliberately different calls to action:
 *
 * - `non-follower` (signed in, not following) is offered a Follow button.
 *   Sending them to sign in would be wrong, they already are.
 * - `signed-out` is the only case that may go to the login page.
 */
export default function ParticipationGate({
  level,
  artistName,
  artistSlug,
  locale,
  followLoading,
  onFollow,
}: ParticipationGateProps) {
  const t = useTranslations('community');

  if (level === 'follower') {
    return null;
  }

  const isSignedOut = level === 'signed-out';

  const description = isSignedOut
    ? t('signInDescription', { artist: artistName })
    : t('followRequiredDescription', { artist: artistName });

  return (
    <section
      data-testid="participation-gate"
      data-level={level}
      aria-labelledby="participation-gate-title"
      className="rounded-xl border border-border bg-card-bg p-4 sm:p-5"
    >
      <h2
        id="participation-gate-title"
        className="text-[15px] font-semibold sm:text-base"
      >
        {t('followRequiredTitle')}
      </h2>

      <p className="mt-1.5 text-sm leading-relaxed text-muted">
        {description}
      </p>

      <div className="mt-4">
        {isSignedOut ? (
          <Link
            href={getLoginPath(
              locale,
              `/${locale}/artists/${artistSlug}/community`
            )}
            data-testid="participation-sign-in"
            className="inline-flex min-h-[44px] w-full items-center justify-center rounded-lg bg-accent-solid px-4 text-sm font-semibold text-on-accent transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background sm:w-auto"
          >
            {t('signIn')}
          </Link>
        ) : (
          <Button
            onClick={onFollow}
            disabled={followLoading}
            variant="primary"
            data-testid="participation-follow"
            className="w-full sm:w-auto"
          >
            {t('follow')}
          </Button>
        )}
      </div>
    </section>
  );
}
