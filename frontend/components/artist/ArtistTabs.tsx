'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';

export type ArtistSection = 'overview' | 'events' | 'community';

interface ArtistTabsProps {
  locale: string;
  slug: string;
  active: ArtistSection;
}

const SECTIONS: {
  key: ArtistSection;
  labelKey: 'tabOverview' | 'tabEvents' | 'tabCommunity';
  path: (slug: string) => string;
}[] = [
  {
    key: 'overview',
    labelKey: 'tabOverview',
    path: (slug) => `/artists/${slug}`,
  },
  {
    key: 'events',
    labelKey: 'tabEvents',
    path: (slug) => `/artists/${slug}/events`,
  },
  {
    key: 'community',
    labelKey: 'tabCommunity',
    path: (slug) => `/artists/${slug}/community`,
  },
];

/**
 * Section navigation for the artist experience.
 *
 * Community is artist-scoped, so it appears here rather than in the global
 * navigation. Every href keeps the active locale.
 */
export default function ArtistTabs({ locale, slug, active }: ArtistTabsProps) {
  const t = useTranslations('artist');

  return (
    <nav
      aria-label={t('tabOverview')}
      data-testid="artist-tabs"
      className="-mb-px flex gap-1 overflow-x-auto border-b border-border"
    >
      {SECTIONS.map((section) => {
        const isActive = section.key === active;

        return (
          <Link
            key={section.key}
            href={`/${locale}${section.path(slug)}`}
            aria-current={isActive ? 'page' : undefined}
            data-testid={`artist-tab-${section.key}`}
            className={[
              'inline-flex min-h-[44px] shrink-0 items-center whitespace-nowrap',
              'border-b-2 px-4 text-sm transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
              isActive
                ? 'border-accent font-semibold text-accent-text'
                : 'border-transparent text-muted hover:border-border-strong hover:text-foreground',
            ].join(' ')}
          >
            {t(section.labelKey)}
          </Link>
        );
      })}
    </nav>
  );
}
