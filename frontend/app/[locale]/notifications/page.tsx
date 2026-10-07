'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { format } from 'date-fns';

import RequireAuth from '@/components/auth/RequireAuth';
import Avatar from '@/components/ui/Avatar';
import Button from '@/components/ui/Button';
import Card from '@/components/ui/Card';
import LoadingState from '@/components/LoadingState';
import EmptyState from '@/components/EmptyState';
import { notificationAPI } from '@/app/lib/api';
import { useUnreadNotificationCount } from '@/app/lib/use-notifications';
import type { Notification } from '@/app/types/notification';

function NotificationsContent() {
  const params = useParams<{ locale: string }>();
  const locale = params?.locale ?? 'en';
  const t = useTranslations('notifications');

  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [markingAll, setMarkingAll] = useState(false);
  const { unreadCount, refresh } = useUnreadNotificationCount();

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);

    try {
      const data = await notificationAPI.getNotifications({ limit: 50 });
      setNotifications(data.notifications ?? []);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const markAsRead = useCallback(
    async (notification: Notification) => {
      if (notification.read) {
        return;
      }

      // Optimistic: the row is already the user's own notification, so the
      // read state can flip immediately and reconcile on failure.
      setNotifications((previous) =>
        previous.map((item) =>
          item.id === notification.id ? { ...item, read: true } : item
        )
      );
      refresh();

      try {
        await notificationAPI.markAsRead(notification.id);
      } catch {
        setNotifications((previous) =>
          previous.map((item) =>
            item.id === notification.id ? { ...item, read: false } : item
          )
        );
        refresh();
      }
    },
    [refresh]
  );

  const markAllAsRead = useCallback(async () => {
    setMarkingAll(true);

    setNotifications((previous) =>
      previous.map((item) => ({ ...item, read: true }))
    );
    refresh();

    try {
      await notificationAPI.markAllAsRead();
    } finally {
      setMarkingAll(false);
      load();
      refresh();
    }
  }, [load, refresh]);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold sm:text-[28px]">{t('title')}</h1>
          <p className="mt-1 text-sm text-muted">{t('subtitle')}</p>
        </div>

        {unreadCount > 0 && (
          <Button
            onClick={markAllAsRead}
            disabled={markingAll}
            variant="outline"
            size="sm"
            data-testid="notifications-mark-all"
          >
            {t('markAllRead')}
          </Button>
        )}
      </header>

      {loading ? (
        <LoadingState message={t('title')} />
      ) : error ? (
        <Card className="p-6 text-center">
          <p className="mb-4 text-muted">{t('emptyDescription')}</p>
          <Button onClick={load} variant="outline">
            {t('markAllRead')}
          </Button>
        </Card>
      ) : notifications.length === 0 ? (
        <EmptyState
          icon="🔔"
          title={t('emptyTitle')}
          description={t('emptyDescription')}
        />
      ) : (
        <ul
          className="flex flex-col gap-2"
          data-testid="notifications-list"
        >
          {notifications.map((notification) => (
            <li key={notification.id}>
              <NotificationRow
                notification={notification}
                locale={locale}
                onRead={() => markAsRead(notification)}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NotificationRow({
  notification,
  locale,
  onRead,
}: {
  notification: Notification;
  locale: string;
  onRead: () => void;
}) {
  const t = useTranslations('notifications');
  const tCommon = useTranslations('common');

  const artistName =
    notification.context.artist_name ??
    (notification.target?.name as string | null) ??
    null;

  const message = describeType(notification.type, artistName, t);

  /*
    A prompt has no actor: nobody did anything, the show simply ended. Naming the
    sender would be inventing one, so these read as a line from GigCrowd itself
    and the unread marker stands in for the avatar slot a person would occupy.
  */
  const isPrompt =
    notification.type === 'event_attendance_check' ||
    notification.type === 'event_review_prompt';

  const actorLabel = notification.actor.username
    ? `@${notification.actor.username}`
    : isPrompt
      ? t('fromGigCrowd')
      : tCommon('unread');

  const targetHref = buildTargetHref(notification, locale);

  return (
    <Card
      className={[
        'p-4 transition-colors',
        notification.read ? '' : 'border-accent/50 bg-highlight',
      ].join(' ')}
      data-testid="notification-item"
      data-type={notification.type}
      data-read={notification.read}
    >
      <div className="flex items-start gap-3">
        {notification.actor.username ? (
          <Link
            href={`/${locale}/profile/${notification.actor.username}`}
            className="shrink-0 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            data-testid="notification-actor-avatar"
          >
            <Avatar
              src={notification.actor.avatar_url ?? undefined}
              alt={notification.actor.username}
              size="md"
            />
          </Link>
        ) : (
          <Avatar alt="" size="md" />
        )}

        <div className="min-w-0 flex-1">
          <p className="text-[15px] leading-snug text-foreground">
            <Link
              href={
                notification.actor.username
                  ? `/${locale}/profile/${notification.actor.username}`
                  : '#'
              }
              aria-disabled={!notification.actor.username}
              data-testid="notification-actor-link"
              className="font-semibold underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              {actorLabel}
            </Link>{' '}
            <span data-testid="notification-message">{message}</span>
          </p>

          {notification.target?.excerpt && (
            <p className="mt-1 line-clamp-2 break-anywhere text-sm text-muted">
              {notification.target.excerpt}
            </p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
            {targetHref && (
              <Link
                href={targetHref}
                data-testid="notification-target-link"
                className="inline-flex min-h-[32px] items-center text-sm font-medium text-accent-text underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                {t('viewTarget')}
              </Link>
            )}

            {!notification.read && (
              <>
                <span
                  data-testid="notification-unread-dot"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-accent-text"
                >
                  <span
                    aria-hidden="true"
                    className="h-2 w-2 rounded-full bg-accent"
                  />
                  {t('unreadBadge')}
                </span>

                {/* An explicit control rather than a click handler on the row:
                    the row also holds the links that navigate away, and a
                    container handler would fire alongside them. */}
                <button
                  type="button"
                  onClick={onRead}
                  data-testid="notification-mark-read"
                  className="min-h-[32px] rounded-md px-1.5 text-xs font-medium text-accent-text underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  {t('markRead')}
                </button>
              </>
            )}

            <time
              dateTime={notification.created_at}
              className="text-xs text-muted-subtle"
            >
              {format(new Date(notification.created_at), 'MMM d, yyyy HH:mm')}
            </time>
          </div>
        </div>
      </div>
    </Card>
  );
}

type TranslateFn = (key: string, values?: Record<string, string | number>) => string;

function describeType(
  type: Notification['type'],
  artistName: string | null,
  t: TranslateFn
) {
  switch (type) {
    /*
      The two prompts. They ask a question rather than report something that
      happened to the reader, so the copy is a question, and the event's name is
      the subject of it.
    */
    case 'event_attendance_check':
      return t('type.eventAttendanceCheck');

    case 'event_review_prompt':
      return t('type.eventReviewPrompt');

    case 'follow':
      return t('type.follow');
    case 'like':
      return artistName
        ? t('type.like', { artist: artistName })
        : t('type.likeNoArtist');
    case 'comment':
      return artistName
        ? t('type.comment', { artist: artistName })
        : t('type.commentNoArtist');
    case 'reply':
    default:
      return artistName
        ? t('type.reply', { artist: artistName })
        : t('type.replyNoArtist');
  }
}

/**
 * Build the locale-preserving destination for a notification's content.
 *
 * The locale prefix comes from the current route, so a notification created
 * in any language opens in the language the reader is browsing in.
 */
function buildTargetHref(
  notification: Notification,
  locale: string
): string | null {
  const target = notification.target;

  if (!target) {
    return null;
  }

  switch (target.kind) {
    case 'community_post': {
      const slug = target.artist_slug;
      return slug
        ? `/${locale}/artists/${slug}/community`
        : null;
    }

    case 'comment': {
      const slug = target.artist_slug;
      return slug ? `/${locale}/artists/${slug}/community` : null;
    }

    case 'artist': {
      const slug = target.artist_slug ?? target.id;
      return slug ? `/${locale}/artists/${slug}` : null;
    }

    case 'event':
      return `/${locale}/events/${target.id}`;

    case 'profile':
    default:
      return target.username ? `/${locale}/profile/${target.username}` : null;
  }
}

export default function NotificationsPage() {
  const params = useParams<{ locale: string }>();
  const locale = params?.locale ?? 'en';

  return (
    <RequireAuth locale={locale}>
      <NotificationsContent />
    </RequireAuth>
  );
}
