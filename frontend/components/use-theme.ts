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
 * injected by `app/[locale]/layout.tsx`, so there is no flash and no hydration
 * conflict.
 */
export function useTheme() {
  // The first render must be identical on the server and the client, so the
  // state starts at the server's value and is corrected from the theme the
  // bootstrap script already applied to <html> on mount. Reading the document
  // during the initializer would render the toggle in the wrong state for a
  // light-mode reader and force React to patch the markup during hydration.
  const [theme, setTheme] = useState<ResolvedTheme>('dark');

  useEffect(() => {
    const applied = document.documentElement.getAttribute('data-theme');

    if (applied === 'light' || applied === 'dark') {
      setTheme(applied);
      return;
    }

    // The pre-paint script only reaches documents that render the layout's
    // <head>. An error document does not, so the theme is resolved and
    // applied here instead of leaving the page without one.
    const resolved = readStoredTheme();

    applyTheme(resolved);
    setTheme(resolved);
  }, []);

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