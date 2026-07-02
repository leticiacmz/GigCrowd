'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { eventAPI } from '../lib/api';
import { format } from 'date-fns';

interface Event {
  _id: string;
  title: string;
  artist_name: string;
  venue_name: string;
  date: string;
  location: string;
  image_url?: string;
  status: string;
  going_count: number;
  maybe_count: number;
}

type EventMode = 'all' | 'past' | 'future';

export default function EventsPage() {
  const router = useRouter();
  const [events, setEvents] = useState<Event[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [eventMode, setEventMode] = useState<EventMode>('all');
  const [specificDate, setSpecificDate] = useState('');

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    loadEvents();
  }, [router]);

  const loadEvents = async () => {
    try {
      setLoading(true);
      const data = await eventAPI.getEvents();
      setEvents(data);
    } catch (error) {
      console.error('Failed to load events:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      loadEvents();
      return;
    }

    try {
      setSearching(true);
      
      // If specific date is provided, use it with intelligent fallback
      // Otherwise, use event_type filter
      if (specificDate) {
        const data = await eventAPI.searchExternal(
          searchQuery,
          undefined, // event_type ignored when specific_date is provided
          specificDate,
          undefined, // start_date
          undefined  // end_date
        );
        setEvents(data.events || []);
      } else {
        // Use event_type filter (past/future)
        const eventType = eventMode === 'all' ? 'future' : eventMode;
        const data = await eventAPI.searchExternal(
          searchQuery,
          eventType,
          undefined, // specific_date
          undefined, // start_date
          undefined  // end_date
        );
        setEvents(data.events || []);
      }
    } catch (error) {
      console.error('Failed to search events:', error);
    } finally {
      setSearching(false);
    }
  };

  // Get date constraints based on event mode
  const getDateConstraints = () => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    if (eventMode === 'past') {
      // Past mode: max date is yesterday
      return {
        max: yesterday.toISOString().split('T')[0]
      };
    } else if (eventMode === 'future') {
      // Future mode: min date is today
      return {
        min: today.toISOString().split('T')[0]
      };
    }
    // All mode: no constraints
    return {};
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
            <Link href="/profile" className="text-gray-400 hover:text-white transition-colors">
              Profile
            </Link>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-6">Discover Events</h1>

        {/* Event Mode Selector */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Event Mode
          </label>
          <select
            value={eventMode}
            onChange={(e) => {
              setEventMode(e.target.value as EventMode);
              setSpecificDate(''); // Reset date when mode changes
            }}
            className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            <option value="all">All Events</option>
            <option value="past">Past Events</option>
            <option value="future">Future Events</option>
          </select>
        </div>

        {/* Search Bar */}
        <form onSubmit={handleSearch} className="mb-8">
          <div className="flex flex-col gap-4">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search for artists..."
              className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            
            {/* Specific Date Selector */}
            {eventMode !== 'all' && (
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Specific Date (optional - uses intelligent fallback)
                </label>
                <input
                  type="date"
                  value={specificDate}
                  onChange={(e) => setSpecificDate(e.target.value)}
                  {...getDateConstraints()}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {eventMode === 'past' 
                    ? 'Only past dates allowed (yesterday and earlier)' 
                    : 'Only future dates allowed (today and later)'}
                </p>
              </div>
            )}
            
            <button
              type="submit"
              disabled={searching}
              className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors disabled:opacity-50"
            >
              {searching ? 'Searching...' : 'Search'}
            </button>
          </div>
        </form>

        {/* Events Grid */}
        {loading ? (
          <div className="text-center py-12">
            <div className="text-gray-400">Loading events...</div>
          </div>
        ) : events.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-400 mb-4">No events found.</p>
            <p className="text-gray-500">Try searching for your favorite artists!</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {events.map((event) => (
              <Link
                key={event._id}
                href={`/events/${event._id}`}
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
                  <h3 className="font-semibold text-white mb-2">{event.title}</h3>
                  <p className="text-sm text-gray-400 mb-1">{event.artist_name}</p>
                  <p className="text-sm text-gray-400 mb-1">{event.venue_name}</p>
                  <p className="text-sm text-gray-400 mb-2">
                    {format(new Date(event.date), 'MMM d, yyyy')}
                  </p>
                  <p className="text-sm text-gray-500">{event.location}</p>
                  <div className="flex gap-4 mt-3 text-xs text-gray-500">
                    <span>{event.going_count} going</span>
                    <span>{event.maybe_count} maybe</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
