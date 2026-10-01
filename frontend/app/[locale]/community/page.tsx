'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useTranslations } from 'next-intl';

import { communityPostAPI } from '../../lib/api';
import LoadingState from '../../../components/LoadingState';
import EmptyState from '../../../components/EmptyState';
import Avatar from '../../../components/ui/Avatar';
import Card from '../../../components/ui/Card';

interface CommunityPost {
  id: string;
  artist_slug: string;
  artist_name?: string;
  user_id: string;
  content: string;
  image_url?: string;
  likes_count: number;
  comments_count: number;
  created_at: string;
  username?: string;
  user_avatar_url?: string;
  liked_by_user: boolean;
}

export default function CommunityPage() {
  const t = useTranslations('community');
  const params = useParams();
  const router = useRouter();
  const locale = (params?.locale as string) || 'en';

  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCommunityPosts = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const data = await communityPostAPI.getFeed({ limit: 50, skip: 0 });
      setPosts(data);
    } catch {
      setError(t('error'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    // Browser-only: guard the auth redirect for the client runtime.
    if (typeof window === 'undefined') {
      return;
    }

    if (!window.localStorage.getItem('token')) {
      router.replace(`/${locale}/login`);
      return;
    }

    loadCommunityPosts();
  }, [router, locale, loadCommunityPosts]);

  function handleLike(postId: string, liked: boolean) {
    const request = liked
      ? communityPostAPI.unlikePost(postId)
      : communityPostAPI.likePost(postId);

    request
      .then(() => {
        setPosts((current) =>
          current.map((post) =>
            post.id === postId
              ? {
                  ...post,
                  liked_by_user: !liked,
                  likes_count: liked
                    ? post.likes_count - 1
                    : post.likes_count + 1
                }
              : post
          )
        );
      })
      .catch(() => {
        // Keep the server state as source of truth on failure.
        loadCommunityPosts();
      });
  }

  return (
    <div className="min-h-screen">
      <main className="mx-auto max-w-4xl px-4 py-8">
        <h1 className="mb-6 text-[28px] font-bold">{t('title')}</h1>

        {error && (
          <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {loading ? (
          <LoadingState message={t('loading')} />
        ) : posts.length === 0 ? (
          <EmptyState
            icon="🎵"
            title={t('emptyTitle')}
            description={t('emptyDescription')}
          />
        ) : (
          <ul className="space-y-4">
            {posts.map((post) => (
              <li key={post.id}>
                <Card>
                  <div className="flex items-start gap-4">
                    <Link
                      href={`/${locale}/profile/${post.username}`}
                      className="shrink-0"
                    >
                      <Avatar
                        src={post.user_avatar_url}
                        fallback={
                          post.username?.charAt(0).toUpperCase() || '?'
                        }
                        size="md"
                      />
                    </Link>

                    <div className="min-w-0 flex-1">
                      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
                        <Link
                          href={`/${locale}/profile/${post.username}`}
                          className="font-semibold hover:text-accent"
                        >
                          @{post.username}
                        </Link>

                        {post.artist_name && (
                          <>
                            <span className="text-gray-500">•</span>
                            <span className="text-gray-400">
                              {t('aboutArtist')}
                            </span>
                            <Link
                              href={`/${locale}/artists/${post.artist_slug}`}
                              className="font-medium hover:text-accent"
                            >
                              {post.artist_name}
                            </Link>
                          </>
                        )}
                      </div>

                      <p className="mb-3 whitespace-pre-wrap break-words text-gray-300">
                        {post.content}
                      </p>

                      {post.image_url && (
                        <img
                          src={post.image_url}
                          alt=""
                          className="mb-3 max-w-full rounded-lg"
                        />
                      )}

                      <div className="flex items-center gap-4 text-sm">
                        <button
                          onClick={() =>
                            handleLike(post.id, post.liked_by_user)
                          }
                          aria-pressed={post.liked_by_user}
                          aria-label={t('title')}
                          className={`flex items-center gap-1 transition-colors hover:text-accent ${
                            post.liked_by_user ? 'text-accent' : 'text-gray-400'
                          }`}
                        >
                          <span aria-hidden="true">
                            {post.liked_by_user ? '♥' : '♡'}
                          </span>
                          {post.likes_count}
                        </button>

                        <Link
                          href={`/${locale}/artists/${post.artist_slug}`}
                          className="flex items-center gap-1 text-gray-400 transition-colors hover:text-accent"
                        >
                          <span aria-hidden="true">💬</span>
                          {post.comments_count}
                        </Link>
                      </div>
                    </div>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}