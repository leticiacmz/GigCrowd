'use client';

import { useTranslations } from 'next-intl';

import Card from '@/components/ui/Card';
import CommentItem from '@/components/community/CommentItem';
import UserChip from '@/components/community/UserChip';
import type {
  CommunityComment,
  CommunityPost,
} from '@/app/types/community';

interface PostCardProps {
  locale: string;
  post: CommunityPost;
  canParticipate: boolean;
  liking: boolean;
  onToggleLike: () => void;

  threadOpen: boolean;
  commentsLoading: boolean;
  comments: CommunityComment[] | undefined;
  onToggleThread: () => void;

  commentValue: string;
  commentSubmitting: boolean;
  onCommentChange: (value: string) => void;
  onSubmitComment: () => void;

  replyTarget: string | null;
  replyValueFor: (commentId: string) => string;
  replySubmitting: boolean;
  onToggleReply: (commentId: string) => void;
  onReplyChange: (commentId: string, value: string) => void;
  onSubmitReply: (commentId: string) => void;
}

/**
 * A community post with its comment thread.
 *
 * Reading (the post itself, the like count, the comments) is available to
 * everyone; liking and commenting require following the artist.
 */
export default function PostCard({
  locale,
  post,
  canParticipate,
  liking,
  onToggleLike,
  threadOpen,
  commentsLoading,
  comments,
  onToggleThread,
  commentValue,
  commentSubmitting,
  onCommentChange,
  onSubmitComment,
  replyTarget,
  replyValueFor,
  replySubmitting,
  onToggleReply,
  onReplyChange,
  onSubmitReply,
}: PostCardProps) {
  const t = useTranslations('community');

  const likeLabel = t('likes', { count: post.likes_count });
  const commentLabel = t('commentCount', { count: post.comments_count });

  return (
    <Card
      className="p-4 sm:p-5"
      data-testid="community-post"
      data-post-id={post.id}
    >
      <UserChip
        locale={locale}
        username={post.username}
        avatarUrl={post.user_avatar_url}
        createdAt={post.created_at}
      />

      <p
        data-testid="community-post-content"
        className="mt-3 whitespace-pre-wrap break-anywhere text-[15px] leading-relaxed text-foreground"
      >
        {post.content}
      </p>

      {post.image_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={post.image_url}
          alt=""
          loading="lazy"
          className="mt-3 max-h-96 w-full rounded-lg object-cover"
        />
      )}

      <div className="mt-3 flex flex-wrap items-center gap-1">
        {canParticipate ? (
          <button
            type="button"
            onClick={onToggleLike}
            disabled={liking}
            aria-pressed={post.liked_by_user}
            data-testid="community-post-like"
            className={[
              'inline-flex min-h-[44px] items-center gap-1.5 rounded-lg px-2.5',
              'text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
              'disabled:cursor-not-allowed disabled:opacity-60',
              post.liked_by_user
                ? 'font-semibold text-accent-text'
                : 'text-muted hover:text-accent-text',
            ].join(' ')}
          >
            <span aria-hidden="true">{post.liked_by_user ? '♥' : '♡'}</span>
            <span>{likeLabel}</span>
          </button>
        ) : (
          <span className="inline-flex min-h-[44px] items-center gap-1.5 px-2.5 text-sm text-muted">
            <span aria-hidden="true">♡</span>
            <span>{likeLabel}</span>
          </span>
        )}

        <button
          type="button"
          onClick={onToggleThread}
          aria-expanded={threadOpen}
          aria-controls={`thread-${post.id}`}
          data-testid="community-post-comments-toggle"
          className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg px-2.5 text-sm text-muted transition-colors hover:text-accent-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <span aria-hidden="true">💬</span>
          <span>{commentLabel}</span>
        </button>
      </div>

      {threadOpen && (
        <div
          id={`thread-${post.id}`}
          data-testid="community-thread"
          className="mt-3 border-t border-border pt-4"
        >
          {canParticipate ? (
            <div
              data-testid="community-comment-form"
              className="mb-4 rounded-lg border border-border bg-card-bg p-2.5"
            >
              <label
                htmlFor={`comment-${post.id}`}
                className="sr-only"
              >
                {t('writeComment')}
              </label>

              <textarea
                id={`comment-${post.id}`}
                data-testid="community-comment-input"
                value={commentValue}
                onChange={(event) => onCommentChange(event.target.value)}
                placeholder={t('writeComment')}
                rows={2}
                maxLength={2000}
                className="w-full resize-y rounded-md border border-border bg-background px-3 py-2.5 text-[15px] leading-relaxed text-foreground placeholder:text-muted-subtle focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />

              <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={onSubmitComment}
                  disabled={commentSubmitting || !commentValue.trim()}
                  data-testid="community-comment-submit"
                  className="inline-flex min-h-[44px] w-full items-center justify-center rounded-lg bg-accent-solid px-4 text-sm font-semibold text-on-accent transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent sm:w-auto"
                >
                  {commentSubmitting ? t('posting') : t('post')}
                </button>
              </div>
            </div>
          ) : (
            <p
              data-testid="community-comment-gate"
              className="mb-4 rounded-lg border border-border bg-card-hover/40 px-3 py-2.5 text-sm text-muted"
            >
              {t('followRequiredDescription', {
                artist: post.artist_slug,
              })}
            </p>
          )}

          {commentsLoading ? (
            <p className="text-sm text-muted-subtle">
              {t('loadingComments')}
            </p>
          ) : !comments || comments.length === 0 ? (
            <p className="text-sm text-muted-subtle">
              {t('noCommentsYet')}
            </p>
          ) : (
            <ul className="flex flex-col gap-3">
              {comments.map((comment) => (
                <CommentItem
                  key={comment.id}
                  locale={locale}
                  comment={comment}
                  canParticipate={canParticipate}
                  canReply
                  replyOpen={replyTarget === comment.id}
                  replyValue={replyValueFor(comment.id)}
                  replySubmitting={replySubmitting}
                  onOpenReply={() => onToggleReply(comment.id)}
                  onReplyChange={(value) => onReplyChange(comment.id, value)}
                  onSubmitReply={() => onSubmitReply(comment.id)}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
