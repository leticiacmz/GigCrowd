'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { userAPI } from '../lib/api';
import { format } from 'date-fns';

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [showLogs, setShowLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [formData, setFormData] = useState({
    full_name: '',
    bio: '',
    location: '',
  });

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    loadProfile();
  }, [router]);

  const loadProfile = async () => {
    try {
      const userData = await userAPI.getMe();
      setUser(userData);
      setFormData({
        full_name: userData.full_name || '',
        bio: userData.bio || '',
        location: userData.location || '',
      });
      
      // Load show logs (this would need a proper API call)
      setShowLogs([]);
    } catch (error) {
      console.error('Failed to load profile:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdate = async () => {
    try {
      await userAPI.updateMe(formData);
      setUser({ ...user, ...formData });
      setEditing(false);
    } catch (error) {
      console.error('Failed to update profile:', error);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    router.push('/login');
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-400">Loading profile...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-gray-800 px-4 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <Link href="/feed" className="text-2xl font-bold bg-gradient-to-r from-purple-500 to-pink-500 bg-clip-text text-transparent">
            GigCrowd
          </Link>
          <nav className="flex items-center gap-4">
            <Link href="/feed" className="text-gray-400 hover:text-white transition-colors">
              Feed
            </Link>
            <Link href="/events" className="text-gray-400 hover:text-white transition-colors">
              Events
            </Link>
            <button
              onClick={handleLogout}
              className="text-gray-400 hover:text-white transition-colors"
            >
              Logout
            </button>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-4 py-8">
        {/* Profile Header */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 mb-6">
          <div className="flex items-start gap-6">
            <div className="w-24 h-24 bg-gradient-to-br from-purple-500 to-pink-500 rounded-full flex items-center justify-center text-white text-4xl font-bold">
              {user.username[0].toUpperCase()}
            </div>
            
            <div className="flex-1">
              <div className="flex items-start justify-between">
                <div>
                  <h1 className="text-2xl font-bold">{user.username}</h1>
                  <p className="text-gray-400">{user.email}</p>
                </div>
                <button
                  onClick={() => setEditing(!editing)}
                  className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg transition-colors"
                >
                  {editing ? 'Cancel' : 'Edit Profile'}
                </button>
              </div>
              
              <div className="flex gap-6 mt-4">
                <div className="text-center">
                  <p className="text-2xl font-bold">{user.followers_count}</p>
                  <p className="text-gray-400 text-sm">Followers</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold">{user.following_count}</p>
                  <p className="text-gray-400 text-sm">Following</p>
                </div>
              </div>
            </div>
          </div>

          {editing && (
            <div className="mt-6 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Full Name</label>
                <input
                  type="text"
                  value={formData.full_name}
                  onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500 transition-colors"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Bio</label>
                <textarea
                  value={formData.bio}
                  onChange={(e) => setFormData({ ...formData, bio: e.target.value })}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500 transition-colors"
                  rows={3}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Location</label>
                <input
                  type="text"
                  value={formData.location}
                  onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500 transition-colors"
                />
              </div>
              <button
                onClick={handleUpdate}
                className="px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
              >
                Save Changes
              </button>
            </div>
          )}

          {!editing && (
            <div className="mt-6">
              {user.full_name && <p className="text-gray-300">{user.full_name}</p>}
              {user.bio && <p className="text-gray-400 mt-2">{user.bio}</p>}
              {user.location && <p className="text-gray-400 mt-2">📍 {user.location}</p>}
              <p className="text-gray-500 text-sm mt-4">
                Joined {format(new Date(user.created_at), 'MMMM yyyy')}
              </p>
            </div>
          )}
        </div>

        {/* Concert History */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-bold mb-4">Concert History</h2>
          {showLogs.length === 0 ? (
            <p className="text-gray-400">No concerts attended yet.</p>
          ) : (
            <div className="space-y-3">
              {showLogs.map((log) => (
                <div key={log.id} className="bg-gray-800 rounded-lg p-3">
                  <h3 className="font-semibold">{log.event_title}</h3>
                  <p className="text-sm text-gray-400">
                    {format(new Date(log.date), 'MMM d, yyyy')}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
