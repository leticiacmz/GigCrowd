'use client';

import React from 'react';

import Link from 'next/link';

import { formatDistanceToNow } from 'date-fns';

import Card from '../ui/Card';
import Avatar from '../ui/Avatar';
import Badge from '../ui/Badge';

import type { FeedActivity } from '../../app/types/feed';


interface FeedActivityCardProps {
  activity: FeedActivity;
}


const ACTIVITY_ICONS: Record<string, string> = {
  user_followed_user: '👥',
  user_followed_artist: '🎤',
  community_post_created: '💬',
  event_attendance: '🎟️',
  review_created: '⭐',
  comment_created: '💭',
  reaction_created: '❤️',
};


function actorHref(activity: FeedActivity) {

  return activity.actor.username
    ? `/profile/${activity.actor.username}`
    : null;

}


function timeAgo(createdAt: string) {

  const date = new Date(createdAt);

  if (Number.isNaN(date.getTime())) {
    return '';
  }

  return formatDistanceToNow(date, { addSuffix: true });

}


function ActivityLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {

  return (
    <Link
      href={href}
      className="font-semibold text-foreground hover:text-accent transition-colors"
    >
      {children}
    </Link>
  );

}


function ActivityBody({ activity }: FeedActivityCardProps) {

  const { payload } = activity;


  switch (activity.activity_type) {

    case 'user_followed_user': {

      const username = payload.username;

      return (
        <p className="text-gray-300">
          started following{' '}
          {username ? (
            <ActivityLink href={`/profile/${username}`}>
              @{username}
            </ActivityLink>
          ) : (
            'a new user'
          )}
        </p>
      );

    }

    case 'user_followed_artist': {

      const slug = activity.object_id;

      return (
        <p className="text-gray-300">
          started following{' '}
          <ActivityLink href={`/artists/${slug}`}>
            {payload.artist_name || slug}
          </ActivityLink>
        </p>
      );

    }

    case 'community_post_created': {

      const slug = activity.target_id || payload.artist_slug;

      return (
        <div>
          <p className="text-gray-300">
            posted in{' '}
            {slug ? (
              <ActivityLink href={`/artists/${slug}`}>
                {slug}
              </ActivityLink>
            ) : (
              'the community'
            )}
          </p>

          {payload.preview && (
            <div className="mt-2 rounded-lg bg-card-hover p-3 text-gray-200 whitespace-pre-line break-words">
              {payload.preview}
            </div>
          )}
        </div>
      );

    }

    case 'event_attendance': {

      const eventId = activity.object_id;

      const status = payload.status || 'going';

      return (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-gray-300">
            is{' '}
            <span className="text-foreground font-semibold">{status}</span>
            {' to '}
            <ActivityLink href={`/events/${eventId}`}>
              {payload.event_title || 'an event'}
            </ActivityLink>
          </p>

          <Badge variant="accent" size="sm">
            {status}
          </Badge>
        </div>
      );

    }

    case 'review_created': {

      const eventId = activity.target_id || payload.event_id;

      return (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-gray-300">
            reviewed{' '}
            {eventId ? (
              <ActivityLink href={`/events/${eventId}`}>
                an event
              </ActivityLink>
            ) : (
              'an event'
            )}
          </p>

          {typeof payload.rating === 'number' && (
            <Badge variant="secondary" size="sm">
              {'★'.repeat(Math.max(0, Math.min(5, payload.rating)))}
              {` ${payload.rating}/5`}
            </Badge>
          )}
        </div>
      );

    }

    default:
      return (
        <p className="text-gray-300">
          shared new activity
        </p>
      );

  }

}


export default function FeedActivityCard({ activity }: FeedActivityCardProps) {

  const href = actorHref(activity);

  const username = activity.actor.username || 'user';

  const avatar = (
    <Avatar
      src={activity.actor.avatar_url}
      fallback={username.charAt(0).toUpperCase()}
      size="md"
    />
  );


  return (
    <Card className="transition-colors hover:border-accent/50">

      <div className="flex items-start gap-3 sm:gap-4">

        <div className="shrink-0">
          {href ? <Link href={href}>{avatar}</Link> : avatar}
        </div>

        <div className="min-w-0 flex-1">

          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">

            <span aria-hidden className="text-base">
              {ACTIVITY_ICONS[activity.activity_type] || '🎵'}
            </span>

            {href ? (
              <ActivityLink href={href}>@{username}</ActivityLink>
            ) : (
              <span className="font-semibold text-foreground">@{username}</span>
            )}

            <span className="text-xs text-gray-500">
              {timeAgo(activity.created_at)}
            </span>

          </div>

          <div className="mt-1 text-sm sm:text-base">
            <ActivityBody activity={activity} />
          </div>

        </div>

      </div>

    </Card>
  );

}
