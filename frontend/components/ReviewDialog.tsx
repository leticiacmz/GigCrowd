'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';

import Button from './ui/Button';
import ReviewEditor from './ReviewEditor';
import type { ReviewPayload, ShowLog } from '@/app/types/review';

interface ReviewDialogProps {
  open: boolean;
  /** What is being reviewed, so the dialog says which show it is about. */
  eventTitle: string;
  showLog: ShowLog | null;
  onClose: () => void;
  onSave: (payload: ReviewPayload) => Promise<void>;
  onDelete: () => Promise<void>;
}

/**
 * The dialog a review is written in.
 *
 * It is a dialog rather than an inline form because "I went" is a one-tap action
 * and the review is optional detail: nobody should have to scroll to find it,
 * and nobody should be blocked from recording attendance by it. Escape and the
 * backdrop close it, the page behind it does not scroll, and focus lands inside
 * so a keyboard reader is not stranded at the top of the document.
 */
export default function ReviewDialog({
  open,
  eventTitle,
  showLog,
  onClose,
  onSave,
  onDelete,
}: ReviewDialogProps) {
  const t = useTranslations('review');

  const [busy, setBusy] = useState(false);

  // Escape closes, and the page behind the dialog must not scroll while it is
  // open or the content the reader was on moves under them.
  useEffect(() => {
    if (!open) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose();
      }
    }

    document.addEventListener('keydown', handleKeyDown);

    const previousOverflow = document.body.style.overflow;

    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4"
      data-testid="review-dialog-backdrop"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-dialog-title"
        data-testid="review-dialog"
        onClick={(event) => event.stopPropagation()}
        className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-2xl border border-border bg-card-bg p-5 sm:rounded-2xl sm:p-6"
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2
              id="review-dialog-title"
              className="text-lg font-bold"
              data-testid="review-dialog-title"
            >
              {showLog?.review ? t('editTitle') : t('writeTitle')}
            </h2>

            <p className="mt-1 truncate text-sm text-muted">{eventTitle}</p>
          </div>

          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={onClose}
            aria-label={t('close')}
            data-testid="review-dialog-close"
          >
            ✕
          </Button>
        </div>

        <ReviewEditor
          initialRating={showLog?.rating ?? 0}
          initialReview={showLog?.review ?? ''}
          initialPhotoUrl={showLog?.photo_url ?? null}
          initialPhotoPublicId={showLog?.photo_public_id ?? null}
          onBusyChange={setBusy}
          onSave={onSave}
          onDelete={showLog?.review || showLog?.photo_url ? onDelete : undefined}
        />

        <div className="mt-6 flex justify-end border-t border-border pt-4">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={onClose}
            data-testid="review-dialog-cancel"
          >
            {t('close')}
          </Button>
        </div>
      </div>
    </div>
  );
}