'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { format } from 'date-fns';

import RequireAuth from '@/components/auth/RequireAuth';
import Avatar from '@/components/ui/Avatar';
import Button from '@/components/ui/Button';
import Card from '@/components/ui/Card';
import Select from '@/components/ui/Select';
import LoadingState from '@/components/LoadingState';
import EmptyState from '@/components/EmptyState';
import { feedAPI, type FeedCategory } from '@/app/lib/api';

const PAGE_SIZE = 15;

interface FeedUser {
  id: string;
  username: string | null;
  avatar_url?: string | null;
  full_name?: string | null;
}

interface FeedArtist {
  slug: string;
  name: string;
}

interface FeedTarget {
  kind:
    | 'community_post'
    | 'comment'
    | 'event'
    | 'profile';
  id: string;
  artist_slug?: string | null;
  artist_slugs?: string[] | null;
  username?: string | null;
  title?: string | null;
  starts_at?: string | null;
  likes_count?: number;
  comments_count?: number;
}

interface FeedItem {
  id: string;
  activity_type: string;
  user: FeedUser;
  artist?: FeedArtist | null;
  content?: string | null;
  rating?: number | null;
  attendance_status?: string | null;
  created_at: string;
  target: FeedTarget | null;
}

/**
 * The feed is one timeline with one filter. Each category narrows the same
 * list of activities; there are no per-category views.
 *
 * Four options, offered as one dropdown rather than a row of pills: it is a
 * single choice, not four places to visit, and a row of tabs took more of the
 * page than the timeline it was choosing between. A native `<select>` also
 * opens the platform's own picker on a phone, which is the one control a
 * thumb already knows.
 *
 * `attendance` is no longer an option of its own. Presence did not leave the
 * feed: it arrives under "all", and under "following" when it comes from
 * somebody the reader follows. It simply is not a category of its own any
 * more, which is what keeps this list at four.
 */
const FILTERS: { key: FeedCategory; labelKey: string }[] = [
  { key: 'all', labelKey: 'filter.all' },
  { key: 'community', labelKey: 'filter.community' },
  { key: 'reviews', labelKey: 'filter.reviews' },
  { key: 'following', labelKey: 'filter.following' },
];

function FeedContent() {
  const params = useParams<{ locale: string }>();
  const locale = params?.locale ?? 'en';
  const t = useTranslations('feed');

  const [items, setItems] = useState<FeedItem[]>([]);
  const [category, setCategory] = useState<FeedCategory>('all');
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(
    async (nextCategory: FeedCategory, skip: number, append: boolean) => {
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
        setError(false);
      }

      try {
        const data = await feedAPI.getFeed({
          skip,
          limit: PAGE_SIZE,
          category: nextCategory,
        });

        const activities: FeedItem[] = data.activities ?? [];

        setItems((previous) =>
          append ? [...previous, ...activities] : activities
        );
        setHasMore(activities.length === PAGE_SIZE);
      } catch {
        if (!append) {
          setError(true);
          setItems([]);
        }
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    []
  );

  useEffect(() => {
    load(category, 0, false);
  }, [category, load]);

  const onFilterChange = useCallback(
    (next: FeedCategory) => {
      // Re-selecting the active filter must not wipe the timeline: setting
      // the same value would not re-trigger the effect, so the list would be
      // cleared and never repopulated.
      if (next === category) {
        return;
      }

      setCategory(next);
    },
    [category]
  );

  const loadMore = useCallback(() => {
    load(category, items.length, true);
  }, [category, items.length, load]);

  const retry = useCallback(() => {
    load(category, 0, false);
  }, [category, load]);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold sm:text-[28px]">{t('title')}</h1>
        <p className="mt-1 text-sm text-muted">{t('subtitle')}</p>
      </header>

      <div className="mb-6 flex flex-wrap items-center gap-2 sm:gap-3">
        <label
          htmlFor="feed-filter-select"
          className="text-sm text-muted"
        >
          {t('filterLabel')}
        </label>

        <Select
          id="feed-filter-select"
          value={category}
          onChange={(event) =>
            onFilterChange(event.target.value as FeedCategory)
          }
          className="sm:w-56"
          data-testid="feed-filter-select"
          aria-label={t('filterLabel')}
          options={FILTERS.map((filter) => ({
            key: filter.key,
            label: t(filter.labelKey),
          }))}
        />
      </div>

      {loading ? (
        <LoadingState message={t('loading')} />
      ) : error ? (
        <Card className="p-6 text-center">
          <p className="mb-4 text-muted">{t('error')}</p>
          <Button onClick={retry} variant="outline">
            {t('retry')}
          </Button>
        </Card>
      ) : items.length === 0 ? (
        <EmptyState
          title={category === 'all' ? t('emptyTitle') : t('emptyFiltered')}
          description={
            category === 'all' ? t('emptyDescription') : undefined
          }
        />
      ) : (
        <ol className="flex flex-col gap-4" data-testid="feed-list">
          {items.map((item) => (
            <li key={item.id}>
              <FeedRow item={item} locale={locale} />
            </li>
          ))}
        </ol>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="mt-6 flex flex-col items-center gap-3">
          {hasMore ? (
            <Button
              onClick={loadMore}
              disabled={loadingMore}
              variant="outline"
              data-testid="feed-load-more"
            >
              {loadingMore ? t('loading') : t('loadMore')}
            </Button>
          ) : (
            <p className="text-sm text-muted-subtle">{t('endOfFeed')}</p>
          )}
        </div>
      )}
    </div>
  );
}

function FeedRow({ item, locale }: { item: FeedItem; locale: string }) {
  const t = useTranslations('feed');

  const { verb, target } = useMemo(
    () => describeActivity(item, t, locale),
    [item, locale, t]
  );

  const actorName = item.user.username
    ? `@${item.user.username}`
    : t('activity.followNoUsername');

  return (
    <Card className="p-4 sm:p-5" data-testid="feed-item">
      <div className="flex items-start gap-3">
        {item.user.username ? (
          <Link
            href={`/${locale}/profile/${item.user.username}`}
            className="shrink-0 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <Avatar
              src={item.user.avatar_url ?? undefined}
              alt={item.user.username}
              size="md"
            />
          </Link>
        ) : (
          <Avatar alt="" size="md" />
        )}

        <div className="min-w-0 flex-1">
          <p className="text-sm leading-snug text-muted">
            {item.user.username ? (
              <Link
                href={`/${locale}/profile/${item.user.username}`}
                className="font-semibold text-foreground underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                data-testid="feed-actor-link"
              >
                {actorName}
              </Link>
            ) : (
              <span className="font-semibold text-foreground">
                {actorName}
              </span>
            )}{' '}
            <span data-testid="feed-verb">{verb}</span>
          </p>

          {item.content && (
            <p className="mt-2 whitespace-pre-wrap break-anywhere text-[15px] leading-relaxed text-foreground">
              {item.content}
            </p>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
            {item.rating ? (
              <span className="text-sm text-warning">
                {'★'.repeat(item.rating)}
                <span className="sr-only">
                  {t('rating', { rating: item.rating })}
                </span>
              </span>
            ) : null}

            {target.href ? (
              <Link
                href={target.href}
                data-testid="feed-target-link"
                className="inline-flex min-h-[32px] items-center text-sm font-medium text-accent-text underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                {target.label}
              </Link>
            ) : null}

            <time
              dateTime={item.created_at}
              data-testid="feed-timestamp"
              className="text-xs text-muted-subtle"
            >
              {format(new Date(item.created_at), 'MMM d, yyyy HH:mm')}
            </time>
          </div>
        </div>
      </div>
    </Card>
  );
}

/**
 * Turn an activity into a sentence plus an optional navigation target.
 *
 * Everything the sentence needs (artist identity, the show, the followed
 * user) comes from the same payload, so a feed row can be fully rendered
 * and navigated from one request.
 */
function describeActivity(
  item: FeedItem,
  t: ReturnType<typeof useTranslations<'feed'>>,
  locale: string
) {
  const artistName = item.artist?.name ?? null;

  switch (item.activity_type) {
    case 'create_community_post': {
      return {
        verb: artistName
          ? t('activity.create_community_post', { artist: artistName })
          : t('activity.create_community_postNoArtist'),
        target: communityTarget(item, artistName, t, locale),
      };
    }

    case 'comment_post': {
      return {
        verb: t('activity.comment_post'),
        target: communityTarget(item, artistName, t, locale),
      };
    }

    case 'like_post': {
      return {
        verb: t('activity.like_post'),
        target: communityTarget(item, artistName, t, locale),
      };
    }

    case 'follow': {
      const followedUsername = item.target?.username ?? null;

      return {
        verb: followedUsername
          ? t('activity.follow', { username: `@${followedUsername}` })
          : t('activity.followNoUsername'),
        target: followedUsername
          ? {
              href: `/${locale}/profile/${followedUsername}`,
              label: t('viewProfile'),
            }
          : { href: undefined, label: '' },
      };
    }

    case 'create_review': {
      return {
        verb: t('activity.create_review'),
        target: eventTarget(item, t, locale),
      };
    }

    case 'attend_event': {
      const status = item.attendance_status as
        | 'going'
        | 'maybe'
        | 'went'
        | null;

      const statusLabel = status ? t(`status.${status}`) : '';

      return {
        verb: [t('activity.attend_event'), statusLabel]
          .filter(Boolean)
          .join(' · '),
        target: eventTarget(item, t, locale),
      };
    }

    default:
      return {
        verb: t('activity.followNoUsername'),
        target: { href: undefined, label: '' },
      };
  }
}

function communityTarget(
  item: FeedItem,
  artistName: string | null,
  t: ReturnType<typeof useTranslations<'feed'>>,
  locale: string
) {
  const slug = item.target?.artist_slug ?? item.artist?.slug ?? null;

  return {
    href: slug ? `/${locale}/artists/${slug}/community` : undefined,
    label: artistName
      ? `${artistName} · ${t('viewPost')}`
      : t('viewPost'),
  };
}

function eventTarget(
  item: FeedItem,
  t: ReturnType<typeof useTranslations<'feed'>>,
  locale: string
) {
  return {
    href: item.target?.id
      ? `/${locale}/events/${item.target.id}`
      : undefined,
    label: item.target?.title
      ? `${item.target.title} · ${t('viewEvent')}`
      : t('viewEvent'),
  };
}

export default function FeedPage() {
  const params = useParams<{ locale: string }>();
  const locale = params?.locale ?? 'en';

  return (
    <RequireAuth locale={locale}>
      <FeedContent />
    </RequireAuth>
  );
}
