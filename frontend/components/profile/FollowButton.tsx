'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { followAPI } from '@/app/lib/api';
import { isAuthenticated } from '@/app/lib/auth';
import { useAuthAction } from '@/app/lib/use-auth-action';

interface FollowButtonProps {
  username: string;
  onFollowChange?: (following: boolean) => void;
}

/**
 * Follow control for a public profile.
 *
 * The button stays visible while signed out so the capability is
 * discoverable, but the follow status lookup and the mutation itself are
 * only performed for an authenticated session. Signed-out clicks go to the
 * localized login without issuing a protected API request.
 */
export default function FollowButton({
  username,
  onFollowChange,
}: FollowButtonProps) {
  const t = useTranslations('profile');
  const params = useParams();
  const locale = (params?.locale as string) || 'en';

  const runAuthAction = useAuthAction({ locale });

  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [following, setFollowing] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;

    function evaluate() {
      const signedIn = isAuthenticated();

      setAuthenticated(signedIn);

      if (!signedIn) {
        // Never call the protected status endpoint without a session.
        setFollowing(false);
        setLoading(false);
        return;
      }

      async function loadFollowStatus() {
        try {
          const response = await followAPI.getStatus(username);

          if (cancelled) {
            return;
          }

          setFollowing(response.following);
          onFollowChange?.(response.following);
        } catch {
          if (!cancelled) {
            setFollowing(false);
          }
        }
      }

      loadFollowStatus();
    }

    evaluate();

    // Re-evaluate on sign-in/sign-out so the control reflects the session
    // even when the profile stays mounted across the transition.
    window.addEventListener('auth-changed', evaluate);

    return () => {
      cancelled = true;
      window.removeEventListener('auth-changed', evaluate);
    };
  }, [username, onFollowChange]);

  const handleFollow = useCallback(() => {
    runAuthAction(async () => {
      try {
        setLoading(true);

        if (following) {
          await followAPI.unfollowUser(username);
          setFollowing(false);
          onFollowChange?.(false);
        } else {
          await followAPI.followUser(username);
          setFollowing(true);
          onFollowChange?.(true);
        }
      } catch {
        // Backend is the source of truth; surface no optimistic state.
        setFollowing(false);
      } finally {
        setLoading(false);
      }
    });
  }, [runAuthAction, following, username, onFollowChange]);

  const label = following ? t('followingLabel') : t('followLabel');

  return (
    <button
      type="button"
      onClick={handleFollow}
      disabled={loading}
      data-testid="follow-button"
      data-authenticated={authenticated ? 'true' : 'false'}
      aria-label={label}
      className="rounded-lg bg-accent px-5 py-2 text-white transition-colors hover:bg-accent/80 disabled:opacity-60"
    >
      {loading ? t('loading') : label}
    </button>
  );
}