'use client';

import { useTranslations } from 'next-intl';

import Avatar from '@/components/ui/Avatar';
import Button from '@/components/ui/Button';

interface PostComposerProps {
  artistName: string;
  currentUsername?: string | null;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  submitting: boolean;
  error: boolean;
}

/**
 * Composer for new community posts. Only rendered for followers of the artist.
 */
export default function PostComposer({
  artistName,
  currentUsername,
  value,
  onChange,
  onSubmit,
  submitting,
  error,
}: PostComposerProps) {
  const t = useTranslations('community');

  return (
    <section
      aria-label={t('shareSomething', { artist: artistName })}
      data-testid="community-composer"
      className="rounded-xl border border-border bg-card-bg p-4 sm:p-5"
    >
      <div className="flex items-start gap-3">
        {currentUsername && (
          <span className="hidden shrink-0 sm:block">
            <Avatar
              alt={currentUsername}
              fallback={currentUsername.charAt(0).toUpperCase()}
              size="md"
            />
          </span>
        )}

        <div className="min-w-0 flex-1">
          <label htmlFor="community-post-content" className="sr-only">
            {t('shareSomething', { artist: artistName })}
          </label>

          <textarea
            id="community-post-content"
            data-testid="community-post-input"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={t('shareSomething', { artist: artistName })}
            rows={3}
            maxLength={2000}
            className="w-full resize-y rounded-lg border border-border bg-background px-3.5 py-3 text-[15px] leading-relaxed text-foreground placeholder:text-muted-subtle focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />

          {error && (
            <p
              role="alert"
              data-testid="community-post-error"
              className="mt-2 text-sm text-accent-text"
            >
              {t('postFailed')}
            </p>
          )}

          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:justify-end">
            <Button
              onClick={onSubmit}
              disabled={submitting || !value.trim()}
              data-testid="community-post-submit"
              className="w-full sm:w-auto"
            >
              {submitting ? t('posting') : t('post')}
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
