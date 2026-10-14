'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useParams } from 'next/navigation';
import Link from 'next/link';

import type { Locale } from '@/app/i18n';

import { mediaAPI, userAPI } from '@/app/lib/api';
import { isAuthenticated, patchStoredUser } from '@/app/lib/auth';
import { useAuthAction } from '@/app/lib/use-auth-action';
import {
  resolveLocale,
  formatEventSchedule,
} from '@/app/lib/dates';
import FollowButton from '@/components/profile/FollowButton';
import ProfileStats from '@/components/profile/ProfileStats';
import ProfilePanel, {
  type Panel,
} from '@/components/profile/ProfilePanel';
import ReviewCard from '@/components/ReviewCard';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import Card from '@/components/ui/Card';
import Avatar from '@/components/ui/Avatar';
import SectionHeader from '@/components/ui/SectionHeader';
import LoadingState from '@/components/LoadingState';
import EmptyState from '@/components/EmptyState';

import type {
  ProfileReview,
  ProfileStats as ProfileStatsType,
  UserProfile,
} from '@/app/types/profile';

interface Form {
  full_name: string;
  bio: string;
  location: string;
}

const EMPTY_FORM: Form = {
  full_name: '',
  bio: '',
  location: '',
};

/**
 * How many reviews the profile shows without being asked.
 *
 * A review is the opinion behind a show log, so the newest few are part of the
 * profile rather than something to go and fetch. The figure above them opens
 * the longer list; this is the short version of the same collection, and it
 * costs one request with the rest of the page.
 */
const LATEST_REVIEWS = 3;

/**
 * The route. It resolves the parameters and hands the profile over to a view
 * keyed by username.
 *
 * The key is the point. A client-side navigation from one profile to another
 * reuses the route component, so every figure, review and panel would otherwise
 * be carried over and repainted under the new profile's heading until the next
 * request resolved. Keying the view by username remounts it instead, so no
 * state can outlive the profile it belongs to.
 */
export default function ProfilePage() {
  const { username, locale: localeParam } = useParams<{
    username: string;
    locale: string;
  }>();

  return (
    <ProfileView
      key={username}
      username={username}
      locale={resolveLocale(localeParam)}
    />
  );
}

/**
 * A profile as a concertgoer's record of what they saw.
 *
 * The figures are clickable and each one opens the rows behind it, the latest
 * reviews are shown without being asked for, and the followed artists are the
 * communities the person belongs to. Everything on the page comes from one
 * profile request and one statistics request, and nothing else is fetched until
 * a reader opens a panel.
 */
function ProfileView({
  username,
  locale,
}: {
  username: string;
  locale: Locale;
}) {
  const t = useTranslations('profile');

  const runAuthAction = useAuthAction({ locale });

  const [user, setUser] = useState<UserProfile | null>(null);
  const [stats, setStats] = useState<ProfileStatsType | null>(null);
  const [reviews, setReviews] = useState<ProfileReview[]>([]);
  const [reviewsLoading, setReviewsLoading] = useState(true);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);

  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  /*
    The avatar is saved on its own, the moment a file is picked, rather than
    waiting for the rest of the form: a photo is its own action with its own
    upload, and seeing it appear immediately is the whole point of having
    chosen one. The error stays next to the avatar, because that is what
    failed - the rest of the profile is untouched by it.
  */
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [avatarError, setAvatarError] = useState<string | null>(null);
  const avatarInput = useRef<HTMLInputElement | null>(null);

  /*
    Which list is open, if any. Tapping the same figure a second time closes it,
    so a panel never covers the profile twice.
  */
  const [panel, setPanel] = useState<Panel>(null);

  const [form, setForm] = useState<Form>(EMPTY_FORM);

  /*
    Every figure, list and review on this page belongs to the one person whose
    profile is on screen. The view is keyed by username, so a response can only
    ever write to the profile it was requested for; `requestId` additionally
    drops anything that comes back for a request this view has already
    replaced, so a slow response cannot settle over a newer one.
  */
  const requestId = useRef(0);

  const loadProfile = useCallback(async () => {
    const id = ++requestId.current;

    const belongsToThisProfile = () => id === requestId.current;

    try {
      /*
        `getMe` is a protected endpoint. Public profiles stay viewable while
        signed out, so the session is only requested when one exists.
      */
      if (isAuthenticated()) {
        try {
          const session = await userAPI.getMe();

          if (!belongsToThisProfile()) {
            return;
          }

          setCurrentUser(session);
        } catch {
          if (belongsToThisProfile()) {
            setCurrentUser(null);
          }
        }
      } else {
        setCurrentUser(null);
      }

      const profile = await userAPI.getProfile(username);

      if (!belongsToThisProfile()) {
        return;
      }

      setUser(profile);
      setForm({
        full_name: profile.full_name || '',
        bio: profile.bio || '',
        location: profile.location || '',
      });

      /*
        The figures and the newest reviews are read together: they are two
        independent collections, so they are fetched side by side rather than
        one after the other. If either fails the profile is still worth
        showing, so the error stops them and leaves the rest of the page.
      */
      try {
        const [statsResponse, reviewsResponse] = await Promise.all([
          userAPI.getProfileStats(username),
          userAPI.getProfileReviews(username, LATEST_REVIEWS),
        ]);

        if (!belongsToThisProfile()) {
          return;
        }

        setStats(statsResponse);
        setReviews(reviewsResponse.reviews ?? []);
      } catch {
        if (!belongsToThisProfile()) {
          return;
        }

        setStats(null);
        setReviews([]);
      } finally {
        if (belongsToThisProfile()) {
          setReviewsLoading(false);
        }
      }
    } catch {
      // The profile itself could not be loaded, so there is nothing to show.
      if (belongsToThisProfile()) {
        setUser(null);
      }
    } finally {
      if (belongsToThisProfile()) {
        setLoading(false);
      }
    }
  }, [username]);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  function handleToggle(next: Exclude<Panel, null>) {
    setPanel((current) => (current === next ? null : next));
  }

  async function handleSave() {
    if (!user) {
      return;
    }

    // Editing a profile is a session-bound mutation.
    await runAuthAction(async () => {
      setSaving(true);

      try {
        const response = await userAPI.updateMe(form);

        setUser({
          ...user,
          ...response.user,
        });

        setEditing(false);
      } finally {
        setSaving(false);
      }
    });
  }

  function handleCancel() {
    if (!user) {
      return;
    }

    setForm({
      full_name: user.full_name || '',
      bio: user.bio || '',
      location: user.location || '',
    });

    setEditing(false);
  }

  function handleAvatarFile(file: File | null) {
    if (!file || !user) {
      return;
    }

    /*
      Uploading the file and saving its URL are two legs of one action, and
      both need the caller's session - the same wrapper the sign-in gate
      uses, so an expired session is offered a login rather than a stack
      trace mid-upload.
    */
    void runAuthAction(async () => {
      setUploadingAvatar(true);
      setAvatarError(null);

      try {
        const uploaded = await mediaAPI.uploadImage(file);

        const response = await userAPI.updateMe({
          avatar_url: uploaded.url,
        });

        setUser({ ...user, ...response.user });

        /*
          Every surface showing the *signed-in* user - the Navbar above all
          - reads the stored copy, not this page's state. Patching it (and
          firing the event login fires) is what makes the new photo appear
          there at once instead of at the next login.
        */
        patchStoredUser({ avatar_url: uploaded.url });
      } catch {
        // The avatar keeps what it had: the failure is said in place
        // rather than clearing a photo that may have worked before.
        setAvatarError(t('photoFailed'));
      } finally {
        setUploadingAvatar(false);
      }
    });
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingState message={t('loading')} />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p
          className="text-muted"
          data-testid="profile-not-found"
        >
          {t('notFound')}
        </p>
      </div>
    );
  }

  const isOwnProfile = currentUser?.username === user.username;

  return (
    <div className="min-h-screen">
      <main className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        <Card className="p-5 sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex min-w-0 gap-4">
              <div className="flex shrink-0 flex-col items-center gap-2">
                <div className="relative">
                  <Avatar
                    src={user.avatar_url ?? undefined}
                    alt={user.username}
                    fallback={user.username.charAt(0).toUpperCase()}
                    size="lg"
                  />

                  {/*
                    Own profile only: nobody else gets a control that would
                    403 anyway. The button reaches the hidden file input the
                    same way the review editor's photo button does.
                  */}
                  {isOwnProfile && (
                    <>
                      <button
                        type="button"
                        onClick={() => avatarInput.current?.click()}
                        disabled={uploadingAvatar}
                        aria-label={
                          uploadingAvatar
                            ? t('photoUploading')
                            : t('changeAvatar')
                        }
                        title={t('changeAvatar')}
                        data-testid="profile-avatar-button"
                        className="absolute -bottom-1 -right-1 flex h-7 w-7 items-center justify-center rounded-full border border-border bg-card-bg text-xs shadow-sm transition-colors hover:bg-card-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-60"
                      >
                        <span aria-hidden="true">
                          {uploadingAvatar ? '⏳' : '📷'}
                        </span>
                      </button>

                      <input
                        ref={avatarInput}
                        type="file"
                        accept="image/*"
                        className="hidden"
                        data-testid="profile-avatar-input"
                        onChange={(event) => {
                          const file = event.target.files?.[0] ?? null;

                          handleAvatarFile(file);

                          // Cleared so the same photo can be re-picked after
                          // a failure without the input staying silent.
                          event.target.value = '';
                        }}
                      />
                    </>
                  )}
                </div>

                {avatarError && (
                  <p
                    role="alert"
                    className="w-24 text-center text-xs text-accent-text"
                    data-testid="profile-avatar-error"
                  >
                    {avatarError}
                  </p>
                )}
              </div>

              <div className="min-w-0">
                <h1 className="break-anywhere text-2xl font-bold sm:text-[28px]">
                  {user.username}
                </h1>

                {user.full_name && (
                  <p className="break-anywhere text-muted">
                    {user.full_name}
                  </p>
                )}

                <p className="text-sm text-muted-subtle">
                  {t('joined', {
                    date: formatEventSchedule(
                      { starts_at: user.created_at },
                      locale,
                      t('dateUnknown'),
                    ),
                  })}
                </p>
              </div>
            </div>

            {isOwnProfile ? (
              editing ? (
                <div className="flex shrink-0 gap-2">
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={saving}
                    onClick={handleSave}
                    data-testid="profile-save"
                  >
                    {t('saveChanges')}
                  </Button>

                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={saving}
                    onClick={handleCancel}
                  >
                    {t('cancel')}
                  </Button>
                </div>
              ) : (
                <Button
                  size="sm"
                  variant="outlineGradient"
                  onClick={() => setEditing(true)}
                  data-testid="profile-edit"
                >
                  {t('editProfile')}
                </Button>
              )
            ) : (
              <div className="shrink-0">
                <FollowButton username={user.username} />
              </div>
            )}
          </div>

          {editing ? (
            <div className="mt-6 space-y-3">
              <Input
                value={form.full_name}
                onChange={(event) =>
                  setForm({ ...form, full_name: event.target.value })
                }
                placeholder={t('fullName')}
                aria-label={t('fullName')}
              />

              <textarea
                value={form.bio}
                onChange={(event) =>
                  setForm({ ...form, bio: event.target.value })
                }
                placeholder={t('bio')}
                aria-label={t('bio')}
                rows={3}
                className="w-full rounded-lg border border-border bg-card-bg p-3 text-foreground placeholder:text-muted-subtle focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />

              <Input
                value={form.location}
                onChange={(event) =>
                  setForm({ ...form, location: event.target.value })
                }
                placeholder={t('location')}
                aria-label={t('location')}
              />
            </div>
          ) : (
            <div className="mt-6 space-y-3">
              {user.bio && (
                <p className="break-anywhere whitespace-pre-line text-muted">
                  {user.bio}
                </p>
              )}

              {user.location && (
                <p className="break-anywhere text-muted">
                  <span aria-hidden="true">📍</span>
                  {' '}
                  {user.location}
                </p>
              )}
            </div>
          )}
        </Card>

        {/*
          The social graph stays in the header, where it was, because a profile
          that follows nobody is still worth reading.
        */}
        <div className="flex gap-2">
          <GraphButton
            testId="profile-followers-toggle"
            pressed={panel === 'followers'}
            onClick={() => handleToggle('followers')}
            value={stats?.followers_count ?? 0}
            label={t('followers')}
          />

          <GraphButton
            testId="profile-following-toggle"
            pressed={panel === 'following'}
            onClick={() => handleToggle('following')}
            value={stats?.following_count ?? 0}
            label={t('following')}
          />
        </div>

        {stats && (
          <ProfileStats
            stats={stats}
            panel={panel}
            onToggle={handleToggle}
          />
        )}

        {/*
          The newest reviews are shown only when nothing is open. A review
          belongs to the Reviews section: while Shows, Festivals, Artists,
          Followers or Following is open, an unrelated list of reviews must not
          sit underneath it, and the panel itself already shows reviews when
          Reviews is the open section.
        */}
        {panel === null && (
          <section
            aria-labelledby="latest-reviews-heading"
            data-testid="profile-latest-reviews"
          >
            <SectionHeader
              id="latest-reviews-heading"
              title={t('latestReviews')}
              count={
                stats ? (
                  <span className="text-sm text-muted-subtle">
                    {stats.reviews_count ?? 0}
                  </span>
                ) : undefined
              }
            />

            {reviewsLoading ? (
              <LoadingState message={t('loading')} />
            ) : reviews.length === 0 ? (
              <EmptyState
                icon="✍"
                title={t('noReviews')}
                description={t('noReviewsHint')}
              />
            ) : (
              <div className="space-y-4">
                {reviews.map((review) => (
                  <ReviewCard
                    key={`${review.event_id}-${review.reviewed_at ?? ''}`}
                    review={review}
                    locale={locale}
                  />
                ))}
              </div>
            )}
          </section>
        )}

        {panel && stats && (
          <ProfilePanel
            panel={panel}
            username={user.username}
            locale={locale}
          />
        )}

        {/*
          A signed-out visitor, or one whose statistics could not be loaded, gets
          the events index rather than an empty page: there is always somewhere
          to go next.
        */}
        {!panel && (
          <p className="text-center text-sm text-muted-subtle">
            <Link
              href={`/${locale}/events`}
              className="text-accent transition-colors hover:text-accent/80"
            >
              {t('browseEvents')}
            </Link>
          </p>
        )}
      </main>
    </div>
  );
}

/** One figure of the social graph, which opens that side of it. */
function GraphButton({
  testId,
  pressed,
  onClick,
  value,
  label,
}: {
  testId: string;
  pressed: boolean;
  onClick: () => void;
  value: number;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={pressed}
      data-testid={testId}
      className={`
        flex
        min-h-[56px]
        flex-1
        flex-col
        items-start
        rounded-lg
        border
        px-3
        py-1.5
        text-left
        transition-colors
        focus-visible:outline-none
        focus-visible:ring-2
        focus-visible:ring-accent
        ${
          pressed
            ? 'border-accent bg-accent/10'
            : 'border-transparent hover:bg-card-hover'
        }
      `}
    >
      <span
        className={`
          text-[22px]
          font-bold
          leading-none
          ${pressed ? 'text-accent-text' : 'text-foreground'}
        `}
      >
        {value}
      </span>

      <span
        className={`
          mt-1
          text-sm
          ${pressed ? 'text-foreground' : 'text-muted'}
        `}
      >
        {label}
      </span>
    </button>
  );
}