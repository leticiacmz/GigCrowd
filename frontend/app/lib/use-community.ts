'use client';

import { useCallback, useEffect, useState } from 'react';

import {
  artistAPI,
  commentAPI,
  communityPostAPI,
  isArtistFollowRequired,
} from './api';
import { isAuthenticated } from './auth';
import type {
  CommunityComment,
  CommunityPost,
  ParticipationLevel,
} from '../types/community';

/**
 * State and actions for one artist's community.
 *
 * Reading is public, so posts and comments always load. Writing requires a
 * session *and* a follow of this artist, and that rule is the backend's: a
 * 403 with the "must follow this artist" detail flips `level` to
 * `non-follower` so the page can offer a Follow button in place instead of
 * bouncing the user to sign in.
 */
export function useCommunity(artistSlug: string) {
  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [signedIn, setSignedIn] = useState(false);
  const [following, setFollowing] = useState(false);
  const [followLoading, setFollowLoading] = useState(false);

  const [postContent, setPostContent] = useState('');
  const [postSubmitting, setPostSubmitting] = useState(false);
  const [postError, setPostError] = useState('');

  const [commentsByPost, setCommentsByPost] = useState<
    Record<string, CommunityComment[]>
  >({});
  const [commentsLoading, setCommentsLoading] = useState<
    Record<string, boolean>
  >({});
  const [openThreads, setOpenThreads] = useState<Record<string, boolean>>({});
  const [commentDraft, setCommentDraft] = useState<Record<string, string>>({});
  const [commentSubmitting, setCommentSubmitting] = useState<
    Record<string, boolean>
  >({});
  const [replyDraft, setReplyDraft] = useState<Record<string, string>>({});
  const [replyTarget, setReplyTarget] = useState<string | null>(null);
  const [replySubmitting, setReplySubmitting] = useState(false);
  const [likingPost, setLikingPost] = useState<string | null>(null);
  const [writeError, setWriteError] = useState('');

  useEffect(() => {
    if (!artistSlug) {
      return;
    }

    const active = isAuthenticated();
    setSignedIn(active);

    loadPosts();

    // Follow status is only meaningful with a session; signed-out visitors
    // still read the whole community.
    if (active) {
      loadFollowStatus();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artistSlug]);

  const loadPosts = useCallback(async () => {
    setLoading(true);
    try {
      const data = await communityPostAPI.getPosts(artistSlug);
      setPosts(data ?? []);
      setError(null);
    } catch {
      setError('load');
    } finally {
      setLoading(false);
    }
  }, [artistSlug]);

  const loadFollowStatus = useCallback(async () => {
    try {
      const data = await artistAPI.getFollowStatus(artistSlug);
      setFollowing(Boolean(data.following));
    } catch {
      setFollowing(false);
    }
  }, [artistSlug]);

  const loadComments = useCallback(
    async (postId: string) => {
      setCommentsLoading((previous) => ({ ...previous, [postId]: true }));
      try {
        const data = await commentAPI.getComments(artistSlug, postId);
        setCommentsByPost((previous) => ({ ...previous, [postId]: data ?? [] }));
      } catch {
        setCommentsByPost((previous) => ({ ...previous, [postId]: [] }));
      } finally {
        setCommentsLoading((previous) => ({ ...previous, [postId]: false }));
      }
    },
    [artistSlug]
  );

  const toggleThread = useCallback(
    (postId: string) => {
      const isOpen = openThreads[postId];

      setOpenThreads((previous) => ({ ...previous, [postId]: !isOpen }));

      // Fetch lazily so a page with many posts does not fan out on load.
      if (!isOpen && commentsByPost[postId] === undefined) {
        loadComments(postId);
      }
    },
    [commentsByPost, loadComments, openThreads]
  );

  const toggleFollow = useCallback(async () => {
    setFollowLoading(true);
    try {
      if (following) {
        await artistAPI.unfollowArtist(artistSlug);
        setFollowing(false);
      } else {
        await artistAPI.followArtist(artistSlug);
        setFollowing(true);
      }
    } catch {
      // Keep the previous state; the header will show the real value on reload.
    } finally {
      setFollowLoading(false);
    }
  }, [artistSlug, following]);

  const createPost = useCallback(async () => {
    const content = postContent.trim();
    if (!content) {
      return;
    }

    setPostSubmitting(true);
    setPostError('');

    try {
      await communityPostAPI.createPost(artistSlug, { content });
      setPostContent('');
      await loadPosts();
    } catch {
      setPostError('post');
    } finally {
      setPostSubmitting(false);
    }
  }, [artistSlug, loadPosts, postContent]);

  const toggleLike = useCallback(
    async (post: CommunityPost) => {
      setLikingPost(post.id);

      const wasLiked = post.liked_by_user;

      // Optimistic, then reconciled with the server response.
      setPosts((previous) =>
        previous.map((item) =>
          item.id === post.id
            ? {
                ...item,
                liked_by_user: !wasLiked,
                likes_count: item.likes_count + (wasLiked ? -1 : 1),
              }
            : item
        )
      );

      try {
        if (wasLiked) {
          await communityPostAPI.unlikePost(artistSlug, post.id);
        } else {
          await communityPostAPI.likePost(artistSlug, post.id);
        }
        setWriteError('');
      } catch (caught) {
        setPosts((previous) =>
          previous.map((item) =>
            item.id === post.id
              ? {
                  ...item,
                  liked_by_user: wasLiked,
                  likes_count: item.likes_count + (wasLiked ? 1 : -1),
                }
              : item
          )
        );

        if (isArtistFollowRequired(errorDetail(caught))) {
          setFollowing(false);
        }
        setWriteError('write');
      } finally {
        setLikingPost(null);
      }
    },
    [artistSlug]
  );

  const createComment = useCallback(
    async (postId: string) => {
      const content = (commentDraft[postId] ?? '').trim();
      if (!content) {
        return;
      }

      setCommentSubmitting((previous) => ({ ...previous, [postId]: true }));

      try {
        await commentAPI.createComment(artistSlug, {
          post_id: postId,
          content,
        });
        setCommentDraft((previous) => ({ ...previous, [postId]: '' }));
        await loadComments(postId);
        setWriteError('');
      } catch (caught) {
        if (isArtistFollowRequired(errorDetail(caught))) {
          setFollowing(false);
        }
        setWriteError('write');
      } finally {
        setCommentSubmitting((previous) => ({ ...previous, [postId]: false }));
      }
    },
    [artistSlug, commentDraft, loadComments]
  );

  const createReply = useCallback(
    async (postId: string, parentCommentId: string) => {
      const content = (replyDraft[parentCommentId] ?? '').trim();
      if (!content) {
        return;
      }

      setReplySubmitting(true);

      try {
        await commentAPI.createComment(artistSlug, {
          post_id: postId,
          content,
          parent_comment_id: parentCommentId,
        });
        setReplyDraft((previous) => ({ ...previous, [parentCommentId]: '' }));
        setReplyTarget(null);
        await loadComments(postId);
        setWriteError('');
      } catch (caught) {
        if (isArtistFollowRequired(errorDetail(caught))) {
          setFollowing(false);
        }
        setWriteError('write');
      } finally {
        setReplySubmitting(false);
      }
    },
    [artistSlug, loadComments, replyDraft]
  );

  const level: ParticipationLevel = !signedIn
    ? 'signed-out'
    : following
      ? 'follower'
      : 'non-follower';

  return {
    posts,
    loading,
    error,
    signedIn,
    following,
    followLoading,
    level,
    canParticipate: level === 'follower',

    postContent,
    setPostContent,
    postSubmitting,
    postError,
    createPost,

    toggleFollow,
    toggleLike,
    likingPost,

    commentsByPost,
    commentsLoading,
    openThreads,
    toggleThread,

    commentDraft,
    setCommentDraft,
    commentSubmitting,
    createComment,

    replyDraft,
    setReplyDraft,
    replyTarget,
    setReplyTarget,
    replySubmitting,
    createReply,

    writeError,
  };
}

/** Pull the backend's `detail` string out of an axios rejection. */
function errorDetail(caught: unknown): unknown {
  const response = (caught as { response?: { data?: { detail?: unknown } } })
    ?.response;

  return response?.data?.detail;
}
