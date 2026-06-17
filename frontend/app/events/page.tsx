'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { eventAPI, userAPI } from '../lib/api';
import { format } from 'date-fns';

interface Event {
  id: string;
  title: string;
  artist_id: string;
  venue_name: string;
  date: string;
  location: string;
  status: string;
  going_count: number;
  image_url?: string;
}

export default function EventsPage() {
  const router = useRouter();
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [userAttendance, setUserAttendance] = useState<Record<string, string>>({});

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    loadEvents();
    loadUserAttendance();
  }, [router]);

  const loadEvents = async () => {
    try {
      const data = await eventAPI.getEvents();
      setEvents(data);
    } catch (error) {
      console.error('Failed to load events:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadUserAttendance = async () => {
    try {
      const data = await eventAPI.getEvents(); // This would need to be show logs API
      // For now, we'll track attendance locally
    } catch (error) {
      console.error('Failed to load attendance:', error);
    }
  };

  const handleAttend = async (eventId: string, status: string) => {
    try {
      await eventAPI.attendEvent(eventId, status);
      setUserAttendance({ ...userAttendance, [eventId]: status });
    } catch (error) {
      console.error('Failed to mark attendance:', error);
    }
  };

  const filteredEvents = events.filter(event =>
    event.title.toLowerCase().includes(search.toLowerCase()) ||
    event.location.toLowerCase().includes(search.toLowerCase()) ||
    event.venue_name.toLowerCase().includes(search.toLowerCase())
  );

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
            <Link href="/profile" className="text-gray-400 hover:text-white transition-colors">
              Profile
            </Link>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-6">Discover Events</h1>

        {/* Search */}
        <div className="mb-6">
          <input
            type="text"
            placeholder="Search events, venues, or locations..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500 transition-colors"
          />
        </div>

        {loading ? (
          <div className="text-center py-12">
            <div className="text-gray-400">Loading events...</div>
          </div>
        ) : filteredEvents.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-400">No events found.</p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {filteredEvents.map((event) => (
              <div
                key={event.id}
                className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden hover:border-gray-700 transition-colors"
              >
                {event.image_url && (
                  <img
                    src={event.image_url}
                    alt={event.title}
                    className="w-full h-48 object-cover"
                  />
                )}
                <div className="p-4">
                  <h3 className="font-semibold text-lg mb-2">{event.title}</h3>
                  <p className="text-gray-400 mb-1">{event.venue_name}</p>
                  <p className="text-gray-400 mb-1">
                    {format(new Date(event.date), 'MMM d, yyyy • h:mm a')}
                  </p>
                  <p className="text-gray-400 mb-3">{event.location}</p>
                  
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500">
                      {event.going_count} going
                    </span>
                    <div className="flex gap-2">
                      {!userAttendance[event.id] ? (
                        <>
                          <button
                            onClick={() => handleAttend(event.id, 'going')}
                            className="px-3 py-1 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded transition-colors"
                          >
                            Going
                          </button>
                          <button
                            onClick={() => handleAttend(event.id, 'maybe')}
                            className="px-3 py-1 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded transition-colors"
                          >
                            Maybe
                          </button>
                        </>
                      ) : (
                        <span className="text-sm text-purple-500">
                          {userAttendance[event.id]}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
