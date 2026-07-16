'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';

import { userAPI } from '@/app/lib/api';
import FollowButton from '@/components/profile/FollowButton';
import ProfileStats from '@/components/profile/ProfileStats';

import { format } from 'date-fns';

export default function ProfilePage() {
  const { username } = useParams<{ username: string }>();

  const [user, setUser] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const me = await userAPI.getMe();
        setCurrentUser(me);

        const profile = await userAPI.getProfile(username);
        setUser(profile);

        const profileStats = await userAPI.getProfileStats(username);
        setStats(profileStats);
      } finally {
        setLoading(false);
      }
    }

    if (username) load();
  }, [username]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400">Loading profile...</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400">User not found.</p>
      </div>
    );
  }

  const isOwnProfile = currentUser?.username === user.username;

  return (
    <div className="min-h-screen">
      <header className="border-b border-gray-800 px-4 py-4">
        <div className="max-w-5xl mx-auto flex justify-between items-center">
          <Link href="/feed" className="text-2xl font-bold bg-gradient-to-r from-purple-500 to-pink-500 bg-clip-text text-transparent">
            GigCrowd
          </Link>

          <nav className="flex gap-4">
            <Link href="/feed" className="text-gray-400 hover:text-white">Feed</Link>
            <Link href="/events" className="text-gray-400 hover:text-white">Events</Link>
          </nav>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8 space-y-8">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-3xl font-bold">{user.username}</h1>
              <p className="text-gray-400">{user.email}</p>
            </div>

            {isOwnProfile ? (
              <Link
                href="/profile/edit"
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg"
              >
                Edit Profile
              </Link>
            ) : (
              <FollowButton username={user.username} />
            )}
          </div>

          <div className="flex gap-8 mt-6">
            <div>
              <p className="text-2xl font-bold">{stats?.followers_count ?? 0}</p>
              <p className="text-gray-400">Followers</p>
            </div>

            <div>
              <p className="text-2xl font-bold">{stats?.following_count ?? 0}</p>
              <p className="text-gray-400">Following</p>
            </div>
          </div>

          <div className="mt-6 space-y-2">
            {user.full_name && <p>{user.full_name}</p>}
            {user.bio && <p className="text-gray-400">{user.bio}</p>}
            {user.location && <p className="text-gray-400">📍 {user.location}</p>}

            <p className="text-sm text-gray-500">
              Joined {format(new Date(user.created_at), 'MMMM yyyy')}
            </p>
          </div>
        </div>

        {stats && <ProfileStats stats={stats} />}
      </main>
    </div>
  );
}
