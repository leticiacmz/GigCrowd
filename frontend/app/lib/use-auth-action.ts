'use client';

import { useCallback } from 'react';
import { useRouter } from 'next/navigation';

import {
  isAuthenticated,
  getCurrentPath,
  getLoginPath,
  sanitizeNext,
} from './auth';

interface UseAuthActionOptions {
  locale: string;
  /** Override the page the user returns to after signing in. */
  next?: string;
}

/**
 * Wraps an action that changes user-specific data (follow, like, comment,
 * create, attendance, ...).
 *
 * When signed out the action is NOT executed and no API call is made: the
 * user is sent straight to the localized login, preserving the locale and
 * the page they were on. The backend still enforces authorization
 * server-side; this only avoids a pointless round trip.
 */
export function useAuthAction({ locale, next }: UseAuthActionOptions) {
  const router = useRouter();

  return useCallback(
    (
      action: () => void | Promise<void>,
      redirectTo: 'login' | 'register' = 'login'
    ) => {
      if (isAuthenticated()) {
        return action();
      }

      const target = sanitizeNext(next) ?? getCurrentPath();

      router.push(
        redirectTo === 'register'
          ? `/${locale}/register?next=${encodeURIComponent(target)}`
          : getLoginPath(locale, target)
      );
    },
    [locale, next, router]
  );
}