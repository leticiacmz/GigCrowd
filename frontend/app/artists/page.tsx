'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { artistAPI } from '../lib/api';

interface Artist {
  _id: string;
  name: string;
  genre?: string;
  image_url?: string;
  followers_count?: number;
}

export default function ArtistsPage() {
  const router = useRouter();
  const [artists, setArtists] = useState<Artist[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    loadArtists();
  }, [router]);

  const loadArtists = async () => {
    try {
      setLoading(true);
      const data = await artistAPI.getArtists();
      setArtists(data);
    } catch (error) {
      console.error('Failed to load artists:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      loadArtists();
      return;
    }

    try {
      setSearching(true);
      const data = await artistAPI.searchArtists(searchQuery);
      setArtists(data);
    } catch (error) {
      console.error('Failed to search artists:', error);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-gray-800 px-4 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
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
            <Link href="/profile" className="text-gray-400 hover:text-white transition-colors">
              Profile
            </Link>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-6">Discover Artists</h1>

        {/* Search Bar */}
        <form onSubmit={handleSearch} className="mb-8">
          <div className="flex gap-4">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search for artists..."
              className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <button
              type="submit"
              disabled={searching}
              className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors disabled:opacity-50"
            >
              {searching ? 'Searching...' : 'Search'}
            </button>
          </div>
        </form>

        {/* Artists Grid */}
        {loading ? (
          <div className="text-center py-12">
            <div className="text-gray-400">Loading artists...</div>
          </div>
        ) : artists.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-400 mb-4">No artists found.</p>
            <p className="text-gray-500">Try searching for your favorite artists!</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {artists.map((artist) => (
              <div
                key={artist._id}
                className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden hover:border-gray-700 transition-colors"
              >
                {artist.image_url && (
                  <img
                    src={artist.image_url}
                    alt={artist.name}
                    className="w-full h-48 object-cover"
                  />
                )}
                <div className="p-4">
                  <h3 className="font-semibold text-white mb-2">{artist.name}</h3>
                  {artist.genre && (
                    <p className="text-sm text-gray-400 mb-2">{artist.genre}</p>
                  )}
                  {artist.followers_count && (
                    <p className="text-sm text-gray-500">
                      {artist.followers_count.toLocaleString()} followers
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
