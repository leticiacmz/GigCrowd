'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { notificationAPI } from '@/app/lib/api';
import { isAuthenticated } from '@/app/lib/auth';

/** How often the unread badge refreshes while the tab is visible. */
const POLL_INTERVAL_MS = 60_000;

/**
 * Tracks the signed-in user's unread notification count.
 *
 * The count comes from the backend (`GET /notifications/unread-count`), so it
 * reflects real notifications rather than anything derived from the feed.
 * Polling only runs while the tab is visible, and always stops on unmount or
 * sign-out.
 */
export function useUnreadNotificationCount() {
  const [unreadCount, setUnreadCount] = useState(0);
  const [signedIn, setSignedIn] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    if (!isAuthenticated()) {
      if (mounted.current) {
        setUnreadCount(0);
        setSignedIn(false);
      }
      return;
    }

    try {
      const count = await notificationAPI.getUnreadCount();
      if (mounted.current) {
        setUnreadCount(count);
        setSignedIn(true);
      }
    } catch {
      // A failed poll must not surface an error state in the navbar; the
      // badge simply keeps its previous value.
    }
  }, []);

  useEffect(() => {
    const syncAuth = () => {
      refresh();
    };

    refresh();
    window.addEventListener('auth-changed', syncAuth);

    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        refresh();
      }
    }, POLL_INTERVAL_MS);

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        refresh();
      }
    };

    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      window.removeEventListener('auth-changed', syncAuth);
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [refresh]);

  return { unreadCount, signedIn, refresh };
}
