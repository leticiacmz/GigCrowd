'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import Button from './ui/Button';
import ReviewStars from './ReviewStars';
import { mediaAPI } from '@/app/lib/api';
import type { ReviewPayload } from '@/app/types/review';

/**
 * How many characters the review text may hold.
 *
 * The backend stores the text as a plain string, so the limit lives here as
 * well: a reader is told while typing instead of discovering it on save.
 */
const MAX_REVIEW_LENGTH = 2000;

interface ReviewEditorProps {
  initialRating: number;
  initialReview: string;
  initialPhotoUrl?: string | null;
  initialPhotoPublicId?: string | null;
  /** Reported to the parent so it can disable its own submit while we work. */
  onBusyChange?: (busy: boolean) => void;
  onSave: (data: ReviewPayload) => Promise<void>;
  onDelete?: () => Promise<void>;
}

/**
 * The form a review is written in: a rating, some words, and optionally a photo.
 *
 * A rating alone is not a review, so the submit stays disabled until there is
 * text or a photo to go with it. The photo is uploaded through the project's
 * media endpoint before the review is saved, and a failure is reported in place
 * rather than silently dropping the picture.
 */
export default function ReviewEditor({
  initialRating,
  initialReview,
  initialPhotoUrl = null,
  initialPhotoPublicId = null,
  onBusyChange,
  onSave,
  onDelete,
}: ReviewEditorProps) {
  const t = useTranslations('review');

  const [rating, setRating] = useState(initialRating);
  const [review, setReview] = useState(initialReview);
  const [photoUrl, setPhotoUrl] = useState<string | null>(initialPhotoUrl);
  const [photoPublicId, setPhotoPublicId] =
    useState<string | null>(initialPhotoPublicId);

  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setRating(initialRating);
    setReview(initialReview);
    setPhotoUrl(initialPhotoUrl);
    setPhotoPublicId(initialPhotoPublicId);
    setError(null);
  }, [initialRating, initialReview, initialPhotoUrl, initialPhotoPublicId]);

  const busy = saving || uploading;

  useEffect(() => {
    onBusyChange?.(busy);
  }, [busy, onBusyChange]);

  const trimmed = review.trim();
  const hasSomethingToSay = trimmed.length > 0 || Boolean(photoUrl);
  const canSubmit = rating >= 1 && hasSomethingToSay && !busy;
  const remaining = MAX_REVIEW_LENGTH - review.length;

  async function handlePickPhoto(file: File) {
    setError(null);
    setUploading(true);

    try {
      const uploaded = await mediaAPI.uploadImage(file);

      setPhotoUrl(uploaded.url);
      setPhotoPublicId(uploaded.public_id);
    } catch {
      // The review is still worth keeping without the photo, so the failure is
      // reported in place rather than discarding what was already typed.
      setPhotoUrl(null);
      setPhotoPublicId(null);
      setError(t('photoFailed'));
    } finally {
      setUploading(false);
    }
  }

  function handleRemovePhoto() {
    setPhotoUrl(null);
    setPhotoPublicId(null);
  }

  async function handleSave() {
    if (!canSubmit) {
      return;
    }

    setError(null);
    setSaving(true);

    try {
      await onSave({
        rating,
        review: trimmed.length > 0 ? trimmed : null,
        photo_url: photoUrl,
        photo_public_id: photoPublicId,
      });
    } catch {
      setError(t('saveFailed'));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setError(null);
    setSaving(true);

    try {
      await onDelete?.();
    } catch {
      setError(t('deleteFailed'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <p className="text-sm font-medium text-foreground">{t('yourRating')}</p>

        <ReviewStars
          rating={rating}
          size="lg"
          disabled={busy}
          onChange={setRating}
        />
      </div>

      <div className="space-y-2">
        <label
          className="text-sm font-medium text-foreground"
          htmlFor="review-text"
        >
          {t('yourReview')}
        </label>

        <textarea
          id="review-text"
          data-testid="review-input"
          value={review}
          maxLength={MAX_REVIEW_LENGTH}
          disabled={busy}
          onChange={(event) => setReview(event.target.value)}
          placeholder={t('placeholder')}
          rows={4}
          className="w-full resize-none break-anywhere rounded-lg border border-border bg-card-bg p-3 text-foreground placeholder:text-muted-subtle focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
        />

        <p className="text-xs text-muted-subtle">
          {t('characters', { count: remaining })}
        </p>
      </div>

      <div className="space-y-3">
        <p className="text-sm font-medium text-foreground">{t('yourPhoto')}</p>

        {photoUrl ? (
          <div className="space-y-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={photoUrl}
              alt={t('photoAlt')}
              data-testid="review-photo-preview"
              className="h-40 w-full rounded-lg border border-border object-cover"
            />

            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={handleRemovePhoto}
              data-testid="review-photo-remove"
            >
              {t('removePhoto')}
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              size="sm"
              variant="outlineGradient"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
              data-testid="review-photo-add"
            >
              {uploading ? t('uploadingPhoto') : t('addPhoto')}
            </Button>

            <p className="text-xs text-muted-subtle">{t('photoHint')}</p>
          </div>
        )}

        {/*
          The control stays in the DOM so replacing a photo does not need a
          second permission prompt path; it is reached by the button above.
        */}
        <input
          ref={fileInput}
          type="file"
          accept="image/*"
          className="hidden"
          data-testid="review-photo-input"
          onChange={(event) => {
            const file = event.target.files?.[0];

            if (file) {
              void handlePickPhoto(file);
            }

            event.target.value = '';
          }}
        />
      </div>

      {error && (
        <p role="alert" className="text-sm text-accent-text" data-testid="review-error">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-end gap-3">
        {onDelete && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={handleDelete}
            data-testid="review-delete"
          >
            {t('deleteReview')}
          </Button>
        )}

        <Button
          type="button"
          size="sm"
          variant="primary"
          disabled={!canSubmit}
          onClick={handleSave}
          data-testid="review-save"
        >
          {saving ? t('saving') : t('saveReview')}
        </Button>
      </div>

      {!hasSomethingToSay && (
        <p className="text-xs text-muted-subtle">{t('needsSomething')}</p>
      )}
    </div>
  );
}