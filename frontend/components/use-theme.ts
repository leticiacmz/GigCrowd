'use client';

import { useCallback, useEffect, useState } from 'react';

export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'gigcrowd-theme';

function getSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined') {
    return 'dark';
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

function readStoredTheme(): ResolvedTheme {
  if (typeof window === 'undefined') {
    return 'dark';
  }

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') {
      return stored;
    }
  } catch {
    // Ignore storage access errors (private mode, blocked cookies, etc.)
  }

  return getSystemTheme();
}

function applyTheme(theme: ResolvedTheme) {
  if (typeof document === 'undefined') {
    return;
  }
  document.documentElement.setAttribute('data-theme', theme);
}

/**
 * Keeps the resolved theme in sync with the pre-paint bootstrap script
 * injected by `app/layout.tsx`, so there is no flash and no hydration conflict.
 */
export function useTheme() {
  // Read the theme the bootstrap script already applied to <html> so the
  // first client render matches the server markup and the toggle icon never
  // flashes the wrong state.
  const [theme, setTheme] = useState<ResolvedTheme>(() => {
    if (typeof document === 'undefined') {
      return 'dark';
    }

    const applied = document.documentElement.getAttribute('data-theme');

    return applied === 'light' ? 'light' : 'dark';
  });

  const toggleTheme = useCallback(() => {
    setTheme((current) => {
      const next: ResolvedTheme = current === 'dark' ? 'light' : 'dark';

      applyTheme(next);

      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // Persisting is best-effort only.
      }

      return next;
    });
  }, []);

  // Follow the OS preference while the user has no explicit choice stored.
  useEffect(() => {
    let hasExplicitChoice = false;
    try {
      hasExplicitChoice =
        window.localStorage.getItem(STORAGE_KEY) === 'light' ||
        window.localStorage.getItem(STORAGE_KEY) === 'dark';
    } catch {
      hasExplicitChoice = false;
    }

    if (hasExplicitChoice) {
      return;
    }

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = (event: MediaQueryListEvent) => {
      const next: ResolvedTheme = event.matches ? 'dark' : 'light';
      applyTheme(next);
      setTheme(next);
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  return { theme, toggleTheme };
}