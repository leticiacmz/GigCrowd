'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { artistAPI } from '@/app/lib/api';
import { getLoginPath, getUser } from '@/app/lib/auth';
import { useCommunity } from '@/app/lib/use-community';
import ArtistTabs from '@/components/artist/ArtistTabs';
import Button from '@/components/ui/Button';
import Card from '@/components/ui/Card';
import EmptyState from '@/components/EmptyState';
import LoadingState from '@/components/LoadingState';
import ParticipationGate from '@/components/community/ParticipationGate';
import PostCard from '@/components/community/PostCard';
import PostComposer from '@/components/community/PostComposer';

interface ArtistProfile {
  name: string;
  slug: string;
  image?: string;
  followers_count?: number;
}

export default function ArtistCommunityPage() {
  const params = useParams<{ locale: string; slug: string }>();
  const locale = params?.locale ?? 'en';
  const artistSlug = params?.slug ?? '';

  const t = useTranslations('community');
  const tArtist = useTranslations('artist');
  const tEvent = useTranslations('event');

  const [artist, setArtist] = useState<ArtistProfile | null>(null);
  const [artistError, setArtistError] = useState(false);
  const [currentUsername, setCurrentUsername] = useState<string | null>(null);

  const community = useCommunity(artistSlug);

  useEffect(() => {
    if (!artistSlug) {
      return;
    }

    const user = getUser();
    setCurrentUsername(user?.username ?? null);
  }, [artistSlug]);

  useEffect(() => {
    if (!artistSlug) {
      return;
    }

    let cancelled = false;

    artistAPI
      .getArtist(artistSlug)
      .then((data) => {
        if (!cancelled) {
          setArtist(data);
          setArtistError(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setArtistError(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [artistSlug]);

  if (artistError || (!artist && !community.loading)) {
    return (
      <div className="mx-auto flex min-h-[60vh] w-full max-w-3xl flex-col items-center justify-center gap-4 px-4">
        <p className="text-center text-muted">{tArtist('notFound')}</p>
        <Link
          href={`/${locale}/artists`}
          className="text-accent-text underline-offset-2 hover:underline"
        >
          {tEvent('backToArtists')}
        </Link>
      </div>
    );
  }

  if (community.loading || !artist) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <LoadingState message={t('loading')} />
      </div>
    );
  }

  const artistName = artist.name;

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
      <Link
        href={`/${locale}/artists/${artistSlug}`}
        className="mb-4 inline-flex min-h-[44px] items-center gap-1 rounded-lg text-sm text-muted transition-colors hover:text-accent-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <span aria-hidden="true">&larr;</span>
        {artistName}
      </Link>

      <header className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold sm:text-3xl">
            {t('forArtist', { artist: artistName })}
          </h1>
          <p className="mt-1 text-sm text-muted">
            {t('aboutArtist', { artist: artistName })}
          </p>
        </div>

        <Button
          onClick={() => {
            if (!community.signedIn) {
              // Only a signed-out visitor is sent to the login page; a
              // signed-in non-follower gets the Follow button in place.
              window.location.assign(
                getLoginPath(
                  locale,
                  `/${locale}/artists/${artistSlug}/community`
                )
              );
              return;
            }
            community.toggleFollow();
          }}
          disabled={community.followLoading}
          variant={community.following ? 'outline' : 'primary'}
          data-testid="community-follow-toggle"
          className="shrink-0"
        >
          {community.following ? t('following') : t('follow')}
        </Button>
      </header>

      <div className="mb-6">
        <ArtistTabs locale={locale} slug={artistSlug} active="community" />
      </div>

      <div className="flex flex-col gap-4">
        <ParticipationGate
          level={community.level}
          artistName={artistName}
          artistSlug={artistSlug}
          locale={locale}
          followLoading={community.followLoading}
          onFollow={community.toggleFollow}
        />

        {community.canParticipate && (
          <PostComposer
            artistName={artistName}
            currentUsername={currentUsername}
            value={community.postContent}
            onChange={community.setPostContent}
            onSubmit={community.createPost}
            submitting={community.postSubmitting}
            error={Boolean(community.postError)}
          />
        )}

        {community.posts.length === 0 ? (
          <EmptyState
            icon="🎵"
            title={t('emptyTitle')}
            description={t('emptyDescription')}
          />
        ) : (
          <div className="flex flex-col gap-4">
            {community.posts.map((post) => (
              <PostCard
                key={post.id}
                locale={locale}
                post={post}
                canParticipate={community.canParticipate}
                liking={community.likingPost === post.id}
                onToggleLike={() => community.toggleLike(post)}
                threadOpen={Boolean(community.openThreads[post.id])}
                commentsLoading={Boolean(community.commentsLoading[post.id])}
                comments={community.commentsByPost[post.id]}
                onToggleThread={() => community.toggleThread(post.id)}
                commentValue={community.commentDraft[post.id] ?? ''}
                commentSubmitting={Boolean(
                  community.commentSubmitting[post.id]
                )}
                onCommentChange={(value) =>
                  community.setCommentDraft((previous) => ({
                    ...previous,
                    [post.id]: value,
                  }))
                }
                onSubmitComment={() => community.createComment(post.id)}
                replyTarget={community.replyTarget}
                replyValueFor={(commentId) =>
                  community.replyDraft[commentId] ?? ''
                }
                replySubmitting={community.replySubmitting}
                onToggleReply={(commentId) =>
                  community.setReplyTarget((current) =>
                    current === commentId ? null : commentId
                  )
                }
                onReplyChange={(commentId, value) =>
                  community.setReplyDraft((previous) => ({
                    ...previous,
                    [commentId]: value,
                  }))
                }
                onSubmitReply={(commentId) =>
                  community.createReply(post.id, commentId)
                }
              />
            ))}
          </div>
        )}

        {community.writeError && (
          <Card className="p-3">
            <p role="alert" className="text-sm text-accent-text">
              {t('writeFailed')}
            </p>
          </Card>
        )}
      </div>
    </main>
  );
}
