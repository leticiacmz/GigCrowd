'use client';

import {
  useCallback,
  useEffect,
  useState,
} from 'react';

import { useRouter } from 'next/navigation';

import { feedAPI } from '../lib/api';
import { isAuthenticated } from '../lib/auth';

import LoadingState from '../../components/LoadingState';
import EmptyState from '../../components/EmptyState';
import Button from '../../components/ui/Button';
import FeedActivityCard from '../../components/feed/FeedActivityCard';

import type {
  ActivityType,
  FeedActivity,
} from '../types/feed';


const PAGE_SIZE = 20;


const FILTERS: { label: string; value: ActivityType | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Posts', value: 'community_post_created' },
  { label: 'Artists', value: 'user_followed_artist' },
  { label: 'Shows', value: 'event_attendance' },
  { label: 'Reviews', value: 'review_created' },
  { label: 'Follows', value: 'user_followed_user' },
];


export default function FeedPage() {

  const router = useRouter();

  const [activities, setActivities] = useState<FeedActivity[]>([]);

  const [filter, setFilter] = useState<ActivityType | 'all'>('all');

  const [loading, setLoading] = useState(true);

  const [loadingMore, setLoadingMore] = useState(false);

  const [error, setError] = useState('');

  const [nextSkip, setNextSkip] = useState<number | null>(null);

  const [authorized, setAuthorized] = useState(false);


  useEffect(() => {

    if (!isAuthenticated()) {
      router.replace('/login');

      return;
    }

    setAuthorized(true);

  }, [router]);


  const loadPage = useCallback(
    async (skip: number) => {

      const page = await feedAPI.getFeed({
        limit: PAGE_SIZE,
        skip,
        activity_type: filter === 'all' ? undefined : [filter],
      });

      setActivities((current) =>
        skip === 0 ? page.items : [...current, ...page.items]
      );

      setNextSkip(page.has_more ? page.next_skip ?? skip + PAGE_SIZE : null);

    },
    [filter]
  );


  useEffect(() => {

    if (!authorized) {
      return;
    }

    let cancelled = false;

    setLoading(true);

    setError('');

    loadPage(0)
      .catch((err: any) => {

        if (cancelled) {
          return;
        }

        setError(
          err?.response?.data?.detail ??
            'Unable to load your feed. Please try again.'
        );

        setActivities([]);

        setNextSkip(null);

      })
      .finally(() => {

        if (!cancelled) {
          setLoading(false);
        }

      });

    return () => {
      cancelled = true;
    };

  }, [authorized, loadPage]);


  async function handleLoadMore() {

    if (nextSkip === null || loadingMore) {
      return;
    }

    setLoadingMore(true);

    setError('');

    try {
      await loadPage(nextSkip);

    } catch (err: any) {
      setError(
        err?.response?.data?.detail ??
          'Unable to load more activity. Please try again.'
      );

    } finally {
      setLoadingMore(false);
    }

  }


  function handleRetry() {

    setActivities([]);

    setNextSkip(null);

    setLoading(true);

    setError('');

    loadPage(0)
      .catch((err: any) => {
        setError(
          err?.response?.data?.detail ??
            'Unable to load your feed. Please try again.'
        );
      })
      .finally(() => setLoading(false));

  }


  return (
    <div className="min-h-screen">

      <main className="mx-auto max-w-2xl px-4 py-6 sm:py-8">

        <h1 className="mb-4 text-2xl font-bold sm:text-[28px]">
          Your Feed
        </h1>

        <div className="mb-6 flex flex-wrap gap-2">

          {FILTERS.map((option) => (
            <button
              key={option.value}
              onClick={() => setFilter(option.value)}
              className={`rounded-full border px-3 py-1 text-sm transition-colors ${
                filter === option.value
                  ? 'border-accent bg-accent/20 text-accent'
                  : 'border-border text-gray-400 hover:border-accent/50 hover:text-white'
              }`}
            >
              {option.label}
            </button>
          ))}

        </div>

        {loading ? (

          <LoadingState message="Loading feed..." />

        ) : error && activities.length === 0 ? (

          <EmptyState
            icon="⚠️"
            title="Something went wrong"
            description={error}
            action={{
              label: 'Try again',
              onClick: handleRetry,
            }}
          />

        ) : activities.length === 0 ? (

          <EmptyState
            icon="🎵"
            title="No activity yet"
            description="Follow other fans and artists to see their concerts, posts and reviews here."
            action={{
              label: 'Discover artists',
              onClick: () => router.push('/artists'),
            }}
          />

        ) : (

          <div className="space-y-4">

            {activities.map((activity) => (
              <FeedActivityCard
                key={activity.id}
                activity={activity}
              />
            ))}

            {error && (
              <p className="text-center text-sm text-red-400">
                {error}
              </p>
            )}

            {nextSkip !== null && (
              <div className="flex justify-center pt-2">
                <Button
                  variant="outline"
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                >
                  {loadingMore ? 'Loading...' : 'Load more'}
                </Button>
              </div>
            )}

          </div>

        )}

      </main>

    </div>
  );

}
