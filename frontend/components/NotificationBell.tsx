'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';

import { useUnreadNotificationCount } from '@/app/lib/use-notifications';

interface NotificationBellProps {
  locale: string;
}

/**
 * Navbar entry point for Notifications, with the live unread count.
 *
 * Only rendered for a signed-in user, since notifications are recipient
 * scoped and there is nothing to show otherwise.
 */
export default function NotificationBell({ locale }: NotificationBellProps) {
  const { unreadCount } = useUnreadNotificationCount();
  const t = useTranslations('nav');

  return (
    <Link
      href={`/${locale}/notifications`}
      aria-label={
        unreadCount > 0
          ? `${t('notifications')}, ${unreadCount}`
          : t('notifications')
      }
      data-testid="notifications-link"
      className="relative inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-card-hover hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        className="h-5 w-5"
      >
        <path d="M18 8.5a6 6 0 1 0-12 0c0 5-2 6.5-2 6.5h16s-2-1.5-2-6.5Z" />
        <path d="M10.3 19a2 2 0 0 0 3.4 0" />
      </svg>

      {unreadCount > 0 && (
        <span
          data-testid="notifications-unread-badge"
          className="absolute -right-0.5 -top-0.5 inline-flex min-w-[20px] items-center justify-center rounded-full bg-accent-solid px-1 text-[11px] font-bold leading-5 text-on-accent"
        >
          {unreadCount > 99 ? '99+' : unreadCount}
        </span>
      )}
    </Link>
  );
}
