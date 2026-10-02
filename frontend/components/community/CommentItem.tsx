'use client';

import { useTranslations } from 'next-intl';

import UserChip from '@/components/community/UserChip';
import type { CommunityComment } from '@/app/types/community';

interface CommentItemProps {
  locale: string;
  comment: CommunityComment;
  canParticipate: boolean;
  canReply: boolean;
  replyOpen: boolean;
  replyValue: string;
  replySubmitting: boolean;
  onOpenReply: () => void;
  onReplyChange: (value: string) => void;
  onSubmitReply: () => void;
}

/**
 * A single comment plus its replies.
 *
 * Layout notes for narrow screens:
 * - The header wraps instead of pushing the date off-screen.
 * - Body text is a sibling of the header, not a flex child of the avatar row,
 *   so a long unbroken string wraps inside the available width.
 * - The reply form is a full-width block with its submit button underneath,
 *   which keeps both controls above the 44px touch minimum without a
 *   horizontally cramped input+button pair.
 */
export default function CommentItem({
  locale,
  comment,
  canParticipate,
  canReply,
  replyOpen,
  replyValue,
  replySubmitting,
  onOpenReply,
  onReplyChange,
  onSubmitReply,
}: CommentItemProps) {
  const t = useTranslations('community');

  return (
    <li
      data-testid="community-comment"
      data-comment-id={comment.id}
      className="min-w-0"
    >
      <article className="min-w-0 rounded-lg bg-card-hover/40 p-3">
        <UserChip
          locale={locale}
          username={comment.username}
          avatarUrl={comment.user_avatar_url}
          createdAt={comment.created_at}
          compact
        />

        <p className="mt-2 whitespace-pre-wrap break-anywhere text-[15px] leading-relaxed text-foreground">
          {comment.content}
        </p>

        {canParticipate && canReply && (
          <div className="mt-1 flex flex-wrap items-center gap-x-1">
            <button
              type="button"
              onClick={onOpenReply}
              data-testid="community-comment-reply"
              aria-expanded={replyOpen}
              className="inline-flex min-h-[44px] items-center rounded-lg px-2 text-sm font-medium text-muted transition-colors hover:text-accent-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              {t('reply')}
            </button>

            {comment.replies_count > 0 && (
              <span className="text-xs text-muted-subtle">
                {t('replies', { count: comment.replies_count })}
              </span>
            )}
          </div>
        )}

        {replyOpen && canParticipate && (
          <div
            data-testid="community-reply-form"
            className="mt-2 rounded-lg border border-border bg-background p-2.5"
          >
            <p className="mb-2 text-xs text-muted-subtle">
              {t('replyTo', {
                username: comment.username
                  ? `@${comment.username}`
                  : t('unknownUser'),
              })}
            </p>

            <label htmlFor={`reply-${comment.id}`} className="sr-only">
              {t('writeReply')}
            </label>

            <textarea
              id={`reply-${comment.id}`}
              data-testid="community-reply-input"
              value={replyValue}
              onChange={(event) => onReplyChange(event.target.value)}
              placeholder={t('writeReply')}
              rows={2}
              maxLength={2000}
              className="w-full resize-y rounded-md border border-border bg-card-bg px-3 py-2.5 text-[15px] leading-relaxed text-foreground placeholder:text-muted-subtle focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
            />

            <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={onSubmitReply}
                disabled={replySubmitting || !replyValue.trim()}
                data-testid="community-reply-submit"
                className="inline-flex min-h-[44px] w-full items-center justify-center rounded-lg bg-accent-solid px-4 text-sm font-semibold text-on-accent transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent sm:w-auto"
              >
                {replySubmitting ? t('posting') : t('reply')}
              </button>
            </div>
          </div>
        )}
      </article>

      {comment.replies.length > 0 && (
        <ul className="mt-2 flex flex-col gap-2 border-l-2 border-border pl-2.5 sm:pl-3">
          {comment.replies.map((reply) => (
            <li
              key={reply.id}
              data-testid="community-reply"
              className="min-w-0 rounded-lg bg-card-hover/25 p-2.5"
            >
              <UserChip
                locale={locale}
                username={reply.username}
                avatarUrl={reply.user_avatar_url}
                createdAt={reply.created_at}
                compact
              />

              <p className="mt-1.5 whitespace-pre-wrap break-anywhere text-sm leading-relaxed text-foreground">
                {reply.content}
              </p>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
