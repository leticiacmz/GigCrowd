'use client';

import { useTranslations } from 'next-intl';

import Button from '@/components/ui/Button';

/**
 * "Finding the artist..." - the state between pressing a name in a lineup
 * and seeing that artist's page.
 *
 * The operation behind it can take minutes on a first open: the backend
 * fetches the artist's whole gigography once, under a claim, and every later
 * open is a plain read. So this state has to be honest rather than brief -
 * it shows from the first moment the flow starts, it says which of the two
 * real phases is running (looking the artist up, then importing them), and
 * it never invents a percentage for work whose length is genuinely unknown.
 *
 * The visual is the app's own: the GigCrowd icon already shipped in
 * `public/icons`, with a ring turning around it. A failure is a state of
 * this same panel, not an unstyled apology - a reader gets a sentence and,
 * when retrying is meaningful, a button.
 *
 * Accessibility: the message lives in a `role="status"` / `aria-live`
 * region, so it is announced when it changes and not re-announced on every
 * render. The ring is decoration and is hidden from assistive technology.
 * The project-wide `prefers-reduced-motion` rule shortens every animation;
 * the ring additionally stops turning outright, leaving a still, drawn
 * ring rather than a spinning one.
 */

export type ArtistSyncPhase = 'searching' | 'importing';

export type ArtistSyncFailure = 'failed' | 'unidentifiable';

export default function ArtistSyncLoading({
  phase = 'searching',
  artistName,
  failure = null,
  onRetry,
  onClose,
}: {
  phase?: ArtistSyncPhase;
  artistName?: string | null;
  failure?: ArtistSyncFailure | null;
  onRetry?: () => void;
  onClose?: () => void;
}) {
  const t = useTranslations('artistSync');

  const message = failure
    ? failure === 'unidentifiable'
      ? t('unidentifiable')
      : t('failed')
    : phase === 'importing'
      ? t('importing')
      : t('searching');

  return (
    <div
      className="flex flex-col items-center justify-center gap-6 px-6 text-center"
      data-testid="artist-sync-loading"
      data-artist-sync-phase={failure ?? phase}
    >
      {!failure && (
        <div className="artist-sync-orbit" aria-hidden="true">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/icons/icon-192x192.png"
            alt=""
            width={44}
            height={44}
            className="h-11 w-11 rounded-xl"
          />
        </div>
      )}

      <div
        role="status"
        aria-live="polite"
        className="flex min-h-[3rem] items-center"
      >
        <p className="max-w-sm text-base font-medium text-foreground">
          {artistName ? `${artistName} - ${message}` : message}
        </p>
      </div>

      {failure && (onRetry || onClose) && (
        <div className="flex flex-wrap items-center justify-center gap-3">
          {onRetry && (
            <Button variant="primary" size="md" onClick={onRetry}>
              {t('retry')}
            </Button>
          )}

          {onClose && (
            <Button variant="ghost" size="md" onClick={onClose}>
              {t('close')}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
