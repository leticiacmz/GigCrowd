'use client';

import Link from 'next/link';

import Avatar from '@/components/ui/Avatar';
import { format } from 'date-fns';

interface UserChipProps {
  locale: string;
  username?: string | null;
  avatarUrl?: string | null;
  createdAt?: string;
  /** Slightly smaller avatar, used for nested replies. */
  compact?: boolean;
  /** Highlight the chip while it is the open reply target. */
  highlighted?: boolean;
}

/**
 * Avatar + clickable `@username` + date, the shared header of every post,
 * comment and reply.
 *
 * The username and the avatar both link to the author's public profile and
 * keep the active locale, so `@x` is navigable everywhere it appears.
 */
export default function UserChip({
  locale,
  username,
  avatarUrl,
  createdAt,
  compact = false,
  highlighted = false,
}: UserChipProps) {
  const size = compact ? 'sm' : 'md';

  const avatar = (
    <Avatar
      src={avatarUrl ?? undefined}
      alt={username ?? ''}
      fallback={username ? username.charAt(0).toUpperCase() : undefined}
      size={size}
    />
  );

  const name = username ? `@${username}` : null;

  return (
    <div className="flex min-w-0 items-center gap-2.5">
      {username ? (
        <Link
          href={`/${locale}/profile/${username}`}
          aria-label={name ?? undefined}
          data-testid="community-avatar-link"
          className="shrink-0 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          {avatar}
        </Link>
      ) : (
        <span className="shrink-0">{avatar}</span>
      )}

      <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
        {username ? (
          <Link
            href={`/${locale}/profile/${username}`}
            data-testid="community-username-link"
            className={[
              'min-h-[32px] truncate rounded text-sm font-semibold',
              'underline-offset-2 hover:underline',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
              highlighted ? 'text-accent-text' : 'text-foreground',
            ].join(' ')}
          >
            {name}
          </Link>
        ) : (
          <span className="text-sm text-muted">&mdash;</span>
        )}

        {createdAt && (
          <time
            dateTime={createdAt}
            data-testid="community-timestamp"
            className="shrink-0 text-xs text-muted-subtle"
          >
            {format(new Date(createdAt), 'MMM d, yyyy HH:mm')}
          </time>
        )}
      </span>
    </div>
  );
}
