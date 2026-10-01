'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { artistAPI, eventAPI, communityPostAPI, commentAPI, userAPI } from '../../../lib/api';
import { isAuthenticated } from '../../../lib/auth';
import { useAuthAction } from '../../../lib/use-auth-action';
import Button from '../../../../components/ui/Button';
import Card from '../../../../components/ui/Card';
import Badge from '../../../../components/ui/Badge';
import LoadingState from '../../../../components/LoadingState';
import EventCard from '../../../../components/EventCard';
import Avatar from '../../../../components/ui/Avatar';
import { format } from 'date-fns';
import { useTranslations } from 'next-intl';

interface ArtistProfile {
  id?: string;
  slug?: string;
  name: string;
  image?: string;
  genres: string[];
  followers_count?: number;
  events?: {
    upcoming: number;
    total: number;
  };
}

interface ArtistEvent {
  id: string;
  title: string;
  starts_at: string;
  ends_at?: string | null;
  event_type?: string;
  ticket_url?: string | null;
  free?: boolean | null;
  sold_out?: boolean | null;
  venue?: {
    id?: string | null;
    slug?: string | null;
    name: string;
    city?: string | null;
    country?: string | null;
  };
  festival?: {
    series_id?: string | null;
    name?: string | null;
    edition?: string | null;
    url?: string | null;
    tracking_count?: number | null;
  } | null;
  location?: {
    city?: string | null;
    country?: string | null;
    latitude?: number | null;
    longitude?: number | null;
  } | null;
  going_count?: number;
  maybe_count?: number;
  went_count?: number;
}

interface CommunityPost {
  id: string;
  artist_slug: string;
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

interface Comment {
  id: string;
  post_id: string;
  user_id: string;
  content: string;
  parent_comment_id?: string | null;
  created_at: string;
  updated_at?: string | null;
  username?: string;
  user_avatar_url?: string;
  replies: Comment[];
  replies_count: number;
}

export default function ArtistProfilePage() {
  const params = useParams();
  const router = useRouter();
  const artistSlug = params.slug as string;
  const locale = (params?.locale as string) || 'en';

  const t = useTranslations('artist');

  const runAuthAction = useAuthAction({ locale });
  const tEvent = useTranslations('event');

  const [artist, setArtist] = useState<ArtistProfile | null>(null);
  const [events, setEvents] = useState<ArtistEvent[]>([]);
  const [relatedArtists, setRelatedArtists] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [relatedLoading, setRelatedLoading] = useState(false);
  const [error, setError] = useState('');
  const [following, setFollowing] = useState(false);
  const [followLoading, setFollowLoading] = useState(false);
  const [currentUser, setCurrentUser] = useState<any>(null);

  // Community posts state
  const [communityPosts, setCommunityPosts] = useState<CommunityPost[]>([]);
  const [postsLoading, setPostsLoading] = useState(false);
  const [postContent, setPostContent] = useState('');
  const [postLoading, setPostLoading] = useState(false);
  const [postError, setPostError] = useState('');
  const [likeLoading, setLikeLoading] = useState<string | null>(null);

  // Comments state
  const [comments, setComments] = useState<Record<string, Comment[]>>({});
  const [commentsLoading, setCommentsLoading] = useState<Record<string, boolean>>({});
  const [commentContent, setCommentContent] = useState<Record<string, string>>({});
  const [commentLoading, setCommentLoading] = useState<Record<string, boolean>>({});
  const [replyContent, setReplyContent] = useState<Record<string, string>>({});
  const [replyLoading, setReplyLoading] = useState<Record<string, boolean>>({});
  const [editingComment, setEditingComment] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [showReplies, setShowReplies] = useState<Record<string, boolean>>({});
  const [sessionActive, setSessionActive] = useState(false);

  useEffect(() => {
    if (artistSlug) {
      loadArtist();
      loadArtistEvents();
    }

    // Session-bound data is only requested when signed in; the rest of
    // the page stays publicly viewable. `/community/posts/{slug}` and the
    // follow status are both protected endpoints, so requesting them without
    // a session would fail with 401 on an otherwise public page.
    const signedIn = isAuthenticated();

    setSessionActive(signedIn);

    if (signedIn) {
      loadCommunityPosts();
      loadFollowStatus();
      loadCurrentUser();
    } else {
      setCommunityPosts([]);
    }
  }, [artistSlug]);

  async function loadArtist() {
    try {
      setLoading(true);

      const data = await artistAPI.getArtist(
        artistSlug
      );

      setArtist(data);

      loadRelatedArtists();

    } catch (error) {

      console.error(
        'Failed to load artist:',
        error
      );

      setError(
        'Could not load artist profile.'
      );

    } finally {

      setLoading(false);

    }
  }

  async function loadArtistEvents() {
    try {

      const data =
        await eventAPI.getArtistEvents(
          artistSlug
        );

      const sortedEvents = [...data].sort(
        (a, b) =>
          new Date(
            a.starts_at
          ).getTime()
          -
          new Date(
            b.starts_at
          ).getTime()
      );

      setEvents(
        sortedEvents
      );

    } catch (error) {

      console.error(
        'Failed to load artist events:',
        error
      );

    }
  }

  async function loadFollowStatus() {
    try {

      const data =
        await artistAPI.getFollowStatus(
          artistSlug
        );

      setFollowing(
        data.following
      );

    } catch (error) {

      console.error(
        'Failed to load follow status:',
        error
      );

    }
  }

  async function loadCurrentUser() {
    try {
      const me = await userAPI.getMe();
      setCurrentUser(me);
    } catch (error) {
      console.error('Failed to load current user:', error);
    }
  }

  async function loadRelatedArtists() {
    try {

      setRelatedLoading(true);

      const data =
        await artistAPI.getRelatedArtists(
          artistSlug
        );

      setRelatedArtists(
        data.related_artists || []
      );

    } catch (error) {

      console.error(
        'Failed to load related artists:',
        error
      );

      setRelatedArtists([]);

    } finally {

      setRelatedLoading(false);

    }
  }

  async function handleFollow() {
    try {

      setFollowLoading(true);

      if (following) {

        await artistAPI.unfollowArtist(
          artistSlug
        );

        setFollowing(false);

      } else {

        await artistAPI.followArtist(
          artistSlug
        );

        setFollowing(true);

      }

    } catch (error) {

      console.error(
        'Failed to update follow:',
        error
      );

    } finally {

      setFollowLoading(false);

    }
  }


  async function loadCommunityPosts() {
    try {
      setPostsLoading(true);
      const data = await communityPostAPI.getPosts(artistSlug);
      setCommunityPosts(data);
    } catch (error) {
      console.error('Failed to load community posts:', error);
    } finally {
      setPostsLoading(false);
    }
  }


  async function handleCreatePost() {
    if (!postContent.trim()) {
      setPostError('Post content cannot be empty');
      return;
    }

    try {
      setPostLoading(true);
      setPostError('');

      await communityPostAPI.createPost({
        artist_slug: artistSlug,
        content: postContent.trim(),
      });

      setPostContent('');
      loadCommunityPosts();

    } catch (error: any) {
      setPostError(
        error.response?.data?.detail ?? 'Failed to create post'
      );
    } finally {
      setPostLoading(false);
    }
  }


  async function handleLikePost(postId: string, currentlyLiked: boolean) {
    try {
      setLikeLoading(postId);

      if (currentlyLiked) {
        await communityPostAPI.unlikePost(postId);
      } else {
        await communityPostAPI.likePost(postId);
      }

      // Update local state
      setCommunityPosts((prev) =>
        prev.map((post) =>
          post.id === postId
            ? {
                ...post,
                liked_by_user: !currentlyLiked,
                likes_count: currentlyLiked
                  ? post.likes_count - 1
                  : post.likes_count + 1,
              }
            : post
        )
      );

    } catch (error) {
      console.error('Failed to update like:', error);
    } finally {
      setLikeLoading(null);
    }
  }


  // ============================================================
  // COMMENTS
  // ============================================================

  async function loadComments(postId: string) {
    try {
      setCommentsLoading((prev) => ({ ...prev, [postId]: true }));
      const data = await commentAPI.getComments(postId);
      setComments((prev) => ({ ...prev, [postId]: data }));
    } catch (error) {
      console.error('Failed to load comments:', error);
    } finally {
      setCommentsLoading((prev) => ({ ...prev, [postId]: false }));
    }
  }


  async function handleCreateComment(postId: string) {
    const content = commentContent[postId];
    if (!content?.trim()) return;

    try {
      setCommentLoading((prev) => ({ ...prev, [postId]: true }));
      await commentAPI.createComment({
        post_id: postId,
        content: content.trim(),
      });
      setCommentContent((prev) => ({ ...prev, [postId]: '' }));
      loadComments(postId);
    } catch (error) {
      console.error('Failed to create comment:', error);
    } finally {
      setCommentLoading((prev) => ({ ...prev, [postId]: false }));
    }
  }


  async function handleCreateReply(commentId: string, postId: string) {
    const content = replyContent[commentId];
    if (!content?.trim()) return;

    try {
      setReplyLoading((prev) => ({ ...prev, [commentId]: true }));
      await commentAPI.createComment({
        post_id: postId,
        content: content.trim(),
        parent_comment_id: commentId,
      });
      setReplyContent((prev) => ({ ...prev, [commentId]: '' }));
      loadComments(postId);
    } catch (error) {
      console.error('Failed to create reply:', error);
    } finally {
      setReplyLoading((prev) => ({ ...prev, [commentId]: false }));
    }
  }


  async function handleUpdateComment(commentId: string, postId: string) {
    if (!editContent.trim()) return;

    try {
      await commentAPI.updateComment(commentId, { content: editContent.trim() });
      setEditingComment(null);
      setEditContent('');
      loadComments(postId);
    } catch (error) {
      console.error('Failed to update comment:', error);
    }
  }


  async function handleDeleteComment(commentId: string, postId: string) {
    try {
      await commentAPI.deleteComment(commentId);
      loadComments(postId);
    } catch (error) {
      console.error('Failed to delete comment:', error);
    }
  }

  if (loading) {

    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingState message={t('loadingArtist')} />
      </div>
    );
  }

  if (error || !artist) {

    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4">

        <p className="text-red-400">
          {error || 'Artist not found.'}
        </p>

        <Link
          href="/artists"
          className="text-accent hover:text-accent/80"
        >{tEvent('backToArtists')}</Link>

      </div>
    );
  }

  // ============================================================
  // UPCOMING / ACTIVE EVENTS
  // ============================================================

  const now = new Date();

  const upcomingEvents = events
    .filter((event) => {

      if (event.ends_at) {

        return (
          new Date(
            event.ends_at
          ).getTime()
          >=
          now.getTime()
        );

      }

      return (
        new Date(
          event.starts_at
        ).getTime()
        >=
        now.getTime()
      );

    })
    .slice(0, 6);

  return (
    <div className="min-h-screen">

      <main className="max-w-5xl mx-auto px-4 py-10">

        <Card className="overflow-hidden p-0">

          {artist.image && (

            <img
              src={artist.image}
              alt={artist.name}
              className="w-full h-80 object-cover"
            />

          )}

          <div className="p-8">

            <div className="flex items-center justify-between mb-6">

              <div>

                <h1 className="text-[36px] font-bold">
                  {artist.name}
                </h1>

                {artist.followers_count !== undefined && (

                  <p className="text-gray-400 text-sm mt-1">
                    {artist.followers_count} followers
                  </p>

                )}

              </div>

              <Button
                onClick={() => runAuthAction(handleFollow)}
                disabled={followLoading}
              >
                {followLoading
                  ? 'Loading...'
                  : following
                  ? 'Following ✓'
                  : 'Follow'}
              </Button>

            </div>

            {artist.genres?.length > 0 && (

              <div className="mb-8">

                <h2 className="text-[14px] text-gray-400 mb-2">{t('genres')}</h2>

                <div className="flex flex-wrap gap-2">

                  {artist.genres.map(
                    (genre) => (

                      <Badge
                        key={genre}
                        variant="outline"
                      >
                        {genre}
                      </Badge>

                    )
                  )}

                </div>

              </div>

            )}

            <section className="mt-8">

              <div className="flex items-center justify-between mb-5">

                <h2 className="text-[24px] font-bold">{t('upcomingEvents')}</h2>

                {artist.events &&
                  artist.events.total > 6 && (

                    <Link
                      href={`/${locale}/artists/${artistSlug}/events`}
                      className="text-sm text-accent hover:text-accent/80"
                    >{t('seeAllEvents')}</Link>

                  )}

              </div>

              {upcomingEvents.length === 0 ? (

                <p className="text-gray-400">{t('noUpcomingEvents')}</p>

              ) : (

                <div
                  className={`${
                    upcomingEvents.length <= 3
                      ? 'grid grid-cols-1 md:grid-cols-3 gap-4'
                      : upcomingEvents.length === 4
                      ? 'grid grid-cols-1 md:grid-cols-4 gap-4'
                      : 'flex gap-4 overflow-x-auto pb-3 snap-x'
                  }`}
                >

                  {upcomingEvents.map(
                    (event) => (

                      <div
                        key={event.id}
                        className={`${
                          upcomingEvents.length > 4
                            ? 'min-w-[280px] snap-start'
                            : ''
                        }`}
                      >

                        <EventCard
                          event={event}
                        />

                      </div>

                    )
                  )}

                </div>

              )}

            </section>

            {/* ============================================================ */}
            {/* COMMUNITY POSTS */}
            {/* ============================================================ */}

            <section className="mt-12">
              <h2 className="text-[24px] font-bold mb-5">{t('community')}</h2>

              {/* Create Post Form */}
              <div className="mb-6">
                <textarea
                  value={postContent}
                  onChange={(e) => setPostContent(e.target.value)}
                  placeholder={`Share something about ${artist.name}...`}
                  className="w-full rounded-lg border border-border bg-card-bg px-4 py-3 text-foreground placeholder-gray-500 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent min-h-[100px] resize-y"
                  maxLength={2000}
                />
                {postError && (
                  <p className="mt-2 text-sm text-red-500">{postError}</p>
                )}
                <div className="mt-3 flex justify-end">
                  <Button
                    onClick={() => runAuthAction(handleCreatePost)}
                    disabled={postLoading || !postContent.trim()}
                    size="sm"
                  >
                    {postLoading ? t('posting') : t('post')}
                  </Button>
                </div>
              </div>

              {/* Posts List */}
              {!sessionActive ? (
                // Posts are session-bound, so the composer stays visible as a
                // discoverable action while signed out.
                <p className="text-gray-400">{t('signInToSeePosts')}</p>
              ) : postsLoading ? (
                <p className="text-gray-400">{t('loadingPosts')}</p>
              ) : communityPosts.length === 0 ? (
                <p className="text-gray-400">{t('noPostsYet')}</p>
              ) : (
                <div className="space-y-4">
                  {communityPosts.map((post) => (
                    <Card key={post.id} className="p-4">
                      <div className="flex items-start gap-3">
                        <Avatar
                          src={post.user_avatar_url}
                          fallback={post.username?.charAt(0).toUpperCase() || '?'}
                          size="sm"
                        />
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-semibold text-sm">
                              @{post.username || 'unknown'}
                            </span>
                            <span className="text-xs text-gray-500">
                              {format(new Date(post.created_at), 'MMM d, yyyy')}
                            </span>
                          </div>
                          <p className="text-gray-300 text-sm whitespace-pre-wrap">
                            {post.content}
                          </p>
                          {post.image_url && (
                            <img
                              src={post.image_url}
                              alt="Post media"
                              className="mt-2 rounded-lg max-w-full"
                            />
                          )}
                          <div className="mt-3 flex items-center gap-4">
                            <button
                              onClick={() => runAuthAction(() => handleLikePost(post.id, post.liked_by_user))}
                              disabled={likeLoading === post.id}
                              data-testid="like-button"
                              className={`flex items-center gap-1 text-sm transition-colors ${
                                post.liked_by_user
                                  ? 'text-accent'
                                  : 'text-gray-400 hover:text-accent'
                              }`}
                            >
                              <span>{post.liked_by_user ? '♥' : '♡'}</span>
                              <span>{post.likes_count}</span>
                            </button>
                            <button
                              onClick={() => {
                                if (!comments[post.id]) {
                                  loadComments(post.id);
                                }
                                setShowReplies((prev) => ({
                                  ...prev,
                                  [post.id]: !prev[post.id],
                                }));
                              }}
                              className="text-sm text-gray-400 hover:text-accent transition-colors"
                            >
                              💬 {post.comments_count} comments
                            </button>
                          </div>

                          {/* Comments Section */}
                          {showReplies[post.id] && (
                            <div className="mt-3 border-t border-border pt-3">
                              {/* Comment Input */}
                              <div className="flex gap-2 mb-3">
                                <input
                                  type="text"
                                  value={commentContent[post.id] || ''}
                                  onChange={(e) =>
                                    setCommentContent((prev) => ({
                                      ...prev,
                                      [post.id]: e.target.value,
                                    }))
                                  }
                                  placeholder="Write a comment..."
                                  className="flex-1 rounded-lg border border-border bg-card-bg px-3 py-2 text-sm text-foreground placeholder-gray-500 focus:border-accent focus:outline-none"
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                      handleCreateComment(post.id);
                                    }
                                  }}
                                />
                                <Button
                                  onClick={() => runAuthAction(() => handleCreateComment(post.id))}
                                  disabled={commentLoading[post.id] || !commentContent[post.id]?.trim()}
                                  size="sm"
                                >
                                  {commentLoading[post.id] ? '...' : 'Post'}
                                </Button>
                              </div>

                              {/* Comments List */}
                              {commentsLoading[post.id] ? (
                                <p className="text-xs text-gray-500">{t('loadingComments')}</p>
                              ) : comments[post.id]?.length === 0 ? (
                                <p className="text-xs text-gray-500">{t('noCommentsYet')}</p>
                              ) : (
                                <div className="space-y-3">
                                  {comments[post.id]?.map((comment) => (
                                    <div key={comment.id} className="flex gap-2">
                                      <Avatar
                                        src={comment.user_avatar_url}
                                        fallback={comment.username?.charAt(0).toUpperCase() || '?'}
                                        size="sm"
                                      />
                                      <div className="flex-1">
                                        <div className="flex items-center gap-2">
                                          <span className="font-semibold text-xs">
                                            @{comment.username || 'unknown'}
                                          </span>
                                          <span className="text-xs text-gray-500">
                                            {format(new Date(comment.created_at), 'MMM d, yyyy')}
                                          </span>
                                        </div>

                                        {editingComment === comment.id ? (
                                          <div className="mt-1">
                                            <input
                                              type="text"
                                              value={editContent}
                                              onChange={(e) => setEditContent(e.target.value)}
                                              className="w-full rounded-lg border border-border bg-card-bg px-2 py-1 text-sm text-foreground focus:border-accent focus:outline-none"
                                            />
                                            <div className="mt-1 flex gap-2">
                                              <button
                                                onClick={() => runAuthAction(() => handleUpdateComment(comment.id, post.id))}
                                                className="text-xs text-accent hover:underline"
                                              >{t('save')}</button>
                                              <button
                                                onClick={() => setEditingComment(null)}
                                                className="text-xs text-gray-400 hover:underline"
                                              >{t('cancel')}</button>
                                            </div>
                                          </div>
                                        ) : (
                                          <p className="text-sm text-gray-300 mt-0.5">
                                            {comment.content}
                                          </p>
                                        )}

                                        <div className="mt-1 flex items-center gap-3">
                                          <button
                                            onClick={() => {
                                              setReplyContent((prev) => ({
                                                ...prev,
                                                [comment.id]: '',
                                              }));
                                              setShowReplies((prev) => ({
                                                ...prev,
                                                [comment.id]: !prev[comment.id],
                                              }));
                                            }}
                                            className="text-xs text-gray-400 hover:text-accent"
                                          >{t('reply')}</button>
                                          {comment.user_id === currentUser?.id && (
                                            <>
                                              <button
                                                onClick={() => {
                                                  setEditingComment(comment.id);
                                                  setEditContent(comment.content);
                                                }}
                                                className="text-xs text-gray-400 hover:text-accent"
                                              >{t('edit')}</button>
                                              <button
                                                onClick={() => runAuthAction(() => handleDeleteComment(comment.id, post.id))}
                                                className="text-xs text-gray-400 hover:text-red-400"
                                              >{t('delete')}</button>
                                            </>
                                          )}
                                        </div>

                                        {/* Reply Input */}
                                        {showReplies[comment.id] && (
                                          <div className="mt-2 flex gap-2">
                                            <input
                                              type="text"
                                              value={replyContent[comment.id] || ''}
                                              onChange={(e) =>
                                                setReplyContent((prev) => ({
                                                  ...prev,
                                                  [comment.id]: e.target.value,
                                                }))
                                              }
                                              placeholder="Write a reply..."
                                              className="flex-1 rounded-lg border border-border bg-card-bg px-2 py-1 text-xs text-foreground placeholder-gray-500 focus:border-accent focus:outline-none"
                                              onKeyDown={(e) => {
                                                if (e.key === 'Enter') {
                                                  handleCreateReply(comment.id, post.id);
                                                }
                                              }}
                                            />
                                            <Button
                                              onClick={() => runAuthAction(() => handleCreateReply(comment.id, post.id))}
                                              disabled={replyLoading[comment.id] || !replyContent[comment.id]?.trim()}
                                              size="sm"
                                            >
                                              {replyLoading[comment.id] ? '...' : 'Reply'}
                                            </Button>
                                          </div>
                                        )}

                                        {/* Replies List */}
                                        {comment.replies?.length > 0 && (
                                          <div className="mt-2 space-y-2 pl-4 border-l border-border">
                                            {comment.replies.map((reply) => (
                                              <div key={reply.id} className="flex gap-2">
                                                <Avatar
                                                  src={reply.user_avatar_url}
                                                  fallback={reply.username?.charAt(0).toUpperCase() || '?'}
                                                  size="sm"
                                                />
                                                <div className="flex-1">
                                                  <div className="flex items-center gap-2">
                                                    <span className="font-semibold text-xs">
                                                      @{reply.username || 'unknown'}
                                                    </span>
                                                    <span className="text-xs text-gray-500">
                                                      {format(new Date(reply.created_at), 'MMM d, yyyy')}
                                                    </span>
                                                  </div>
                                                  <p className="text-sm text-gray-300 mt-0.5">
                                                    {reply.content}
                                                  </p>
                                                  {reply.user_id === currentUser?.id && (
                                                    <div className="mt-1 flex items-center gap-3">
                                                      <button
                                                        onClick={() => {
                                                          setEditingComment(reply.id);
                                                          setEditContent(reply.content);
                                                        }}
                                                        className="text-xs text-gray-400 hover:text-accent"
                                                      >{t('edit')}</button>
                                                      <button
                                                        onClick={() => handleDeleteComment(reply.id, post.id)}
                                                        className="text-xs text-gray-400 hover:text-red-400"
                                                      >{t('delete')}</button>
                                                    </div>
                                                  )}
                                                </div>
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              )}
            </section>

            {relatedArtists.length > 0 && (

              <section className="mt-12">

                <h2 className="text-[24px] font-bold mb-5">{t('relatedArtists')}</h2>

                {relatedLoading ? (

                  <p className="text-gray-400">{t('loadingRelated')}</p>

                ) : (

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">

                    {relatedArtists.map(
                      (
                        relatedArtist,
                        index
                      ) => (

                        <Link
                          key={index}
                          href={`/artists/${relatedArtist.slug}`}
                          className="block"
                        >

                          <Card
                            hoverable
                            className="p-4 text-center"
                          >

                            {relatedArtist.image && (

                              <img
                                src={
                                  relatedArtist.image
                                }
                                alt={
                                  relatedArtist.name
                                }
                                className="w-full h-32 object-cover rounded-lg mb-3"
                              />

                            )}

                            <p className="font-semibold text-sm line-clamp-1">
                              {
                                relatedArtist.name
                              }
                            </p>

                          </Card>

                        </Link>

                      )
                    )}

                  </div>

                )}

              </section>

            )}

          </div>

        </Card>

      </main>

    </div>
  );
}