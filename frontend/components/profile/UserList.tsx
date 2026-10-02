'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';

import { userAPI } from '@/app/lib/api';
import Avatar from '@/components/ui/Avatar';

export type ConnectionDirection = 'followers' | 'following';

interface Connection {
  id: string;
  username: string;
  full_name?: string | null;
  avatar_url?: string | null;
}

interface UserListProps {
  locale: string;
  username: string;
  direction: ConnectionDirection;
}

/**
 * The people behind a profile's follower / following count.
 *
 * Every entry is a link to that person's public profile and keeps the active
 * locale, so `@x` is navigable from the social graph too.
 */
export default function UserList({
  locale,
  username,
  direction,
}: UserListProps) {
  const t = useTranslations('profile');

  const [users, setUsers] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);

    try {
      const data = await userAPI.getConnections(username, direction);
      setUsers(data.users ?? []);
    } catch {
      setUsers([]);
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [direction, username]);

  useEffect(() => {
    load();
  }, [load]);

  const emptyLabel =
    direction === 'followers' ? t('noFollowers') : t('noFollowing');

  return (
    <section
      aria-label={
        direction === 'followers'
          ? t('followersTitle')
          : t('followingTitle')
      }
      data-testid={`profile-${direction}`}
      className="mt-6"
    >
      <h2 className="mb-3 text-lg font-semibold">
        {direction === 'followers'
          ? t('followersTitle')
          : t('followingTitle')}
      </h2>

      {loading ? (
        <p className="text-sm text-muted">{t('loadingConnections')}</p>
      ) : failed ? (
        <p className="text-sm text-muted">{emptyLabel}</p>
      ) : users.length === 0 ? (
        <p className="text-sm text-muted">{emptyLabel}</p>
      ) : (
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {users.map((connection) => (
            <li key={connection.id}>
              <Link
                href={`/${locale}/profile/${connection.username}`}
                data-testid="profile-connection-link"
                className="flex min-h-[56px] items-center gap-3 rounded-lg border border-border bg-card-bg px-3 py-2 transition-colors hover:bg-card-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                <Avatar
                  src={connection.avatar_url ?? undefined}
                  alt={connection.username}
                  fallback={connection.username.charAt(0).toUpperCase()}
                  size="md"
                />

                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-foreground">
                    @{connection.username}
                  </span>
                  {connection.full_name && (
                    <span className="block truncate text-xs text-muted">
                      {connection.full_name}
                    </span>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}


