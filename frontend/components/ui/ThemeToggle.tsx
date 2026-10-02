'use client';

import { useTranslations } from 'next-intl';

import { useTheme } from '@/components/use-theme';

/**
 * Sun/moon theme switch.
 *
 * Reuses the existing `use-theme` state and the `gigcrowd-theme`
 * localStorage key, so there is a single source of truth for the theme and
 * the pre-paint bootstrap script in the root layout stays in sync.
 *
 * Sizing notes: the button keeps a 44x44 hit area and its icon box is fixed,
 * so switching themes never shifts the navbar layout.
 */
export default function ThemeToggle({ className = '' }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const t = useTranslations('common');

  const isDark = theme === 'dark';

  const label = isDark ? t('switchToLight') : t('switchToDark');

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={label}
      title={label}
      data-testid="theme-toggle"
      data-theme-state={theme}
      className={[
        'group',
        'relative inline-flex h-11 w-11 shrink-0 items-center justify-center',
        'rounded-full border border-border bg-card-bg',
        'text-foreground transition-colors duration-200',
        'hover:bg-card-hover hover:border-accent/60',
        'focus-visible:outline-none focus-visible:ring-2',
        'focus-visible:ring-accent focus-visible:ring-offset-2',
        'focus-visible:ring-offset-background',
        className,
      ].join(' ')}
    >
      {/* Both icons occupy the same grid cell so the button never resizes. */}
      <span className="relative block h-5 w-5">
        <SunIcon
          className={[
            'absolute inset-0 h-5 w-5 transition-all duration-200',
            isDark ? 'scale-50 rotate-90 opacity-0' : 'scale-100 rotate-0 opacity-100',
          ].join(' ')}
        />
        <MoonIcon
          className={[
            'absolute inset-0 h-5 w-5 transition-all duration-200',
            isDark ? 'scale-100 rotate-0 opacity-100' : 'scale-50 -rotate-90 opacity-0',
          ].join(' ')}
        />
      </span>
    </button>
  );
}

function SunIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M18.8 5.2l-1.4 1.4M6.6 17.4l-1.4 1.4" />
    </svg>
  );
}

function MoonIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      <path d="M20.5 14.6A8.5 8.5 0 0 1 9.4 3.5a8.5 8.5 0 1 0 11.1 11.1Z" />
    </svg>
  );
}
