'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { eventAPI } from '../../lib/api';
import { format } from 'date-fns';

interface Event {
  _id: string;
  title: string;
  artist_name: string;
  venue_name: string;
  date: string;
  location: string;
  city: string;
  country: string;
  description?: string;
  image_url?: string;
  ticket_url?: string;
  status: string;
  going_count: number;
  maybe_count: number;
  went_count: number;
  setlist?: string[];
  setlist_count?: number;
}

export default function EventDetailPage() {
  const router = useRouter();
  const params = useParams();
  const eventId = params.id as string;
  
  const [event, setEvent] = useState<Event | null>(null);
  const [loading, setLoading] = useState(true);
  const [attendStatus, setAttendStatus] = useState<'going' | 'maybe' | 'went' | null>(null);
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    loadEvent();
  }, [eventId, router]);

  const loadEvent = async () => {
    try {
      setLoading(true);
      const data = await eventAPI.getEvent(eventId);
      setEvent(data);
    } catch (error) {
      console.error('Failed to load event:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAttend = async (status: 'going' | 'maybe' | 'went') => {
    try {
      setSubmitting(true);
      await eventAPI.attendEvent(eventId, status, notes || undefined);
      setAttendStatus(status);
      loadEvent(); // Reload to update counts
    } catch (error) {
      console.error('Failed to mark attendance:', error);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-400">Loading event...</div>
      </div>
    );
  }

  if (!event) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-400">Event not found</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-gray-800 px-4 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link href="/events" className="text-2xl font-bold bg-gradient-to-r from-purple-500 to-pink-500 bg-clip-text text-transparent">
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
        <Link
          href="/events"
          className="inline-block mb-6 text-purple-400 hover:text-purple-300"
        >
          ← Back to Events
        </Link>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Event Details */}
          <div className="lg:col-span-2">
            {event.image_url && (
              <img
                src={event.image_url}
                alt={event.title}
                className="w-full h-64 object-cover rounded-lg mb-6"
              />
            )}

            <h1 className="text-4xl font-bold mb-4">{event.title}</h1>
            
            <div className="space-y-4 mb-6">
              <div>
                <h2 className="text-lg font-semibold text-white">Artist</h2>
                <p className="text-gray-400">{event.artist_name}</p>
              </div>
              
              <div>
                <h2 className="text-lg font-semibold text-white">Venue</h2>
                <p className="text-gray-400">{event.venue_name}</p>
              </div>
              
              <div>
                <h2 className="text-lg font-semibold text-white">Date</h2>
                <p className="text-gray-400">
                  {format(new Date(event.date), 'MMMM d, yyyy • h:mm a')}
                </p>
              </div>
              
              <div>
                <h2 className="text-lg font-semibold text-white">Location</h2>
                <p className="text-gray-400">{event.location}</p>
                <p className="text-sm text-gray-500">{event.city}, {event.country}</p>
              </div>
              
              {event.description && (
                <div>
                  <h2 className="text-lg font-semibold text-white">Description</h2>
                  <p className="text-gray-400">{event.description}</p>
                </div>
              )}

              {event.setlist && event.setlist.length > 0 && (
                <div>
                  <h2 className="text-lg font-semibold text-white mb-4">
                    Setlist ({event.setlist_count || event.setlist.length} songs)
                  </h2>
                  <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                    <ol className="space-y-2">
                      {event.setlist.map((song, index) => (
                        <li key={index} className="text-gray-300 flex items-start gap-3">
                          <span className="text-purple-400 font-semibold min-w-[24px]">
                            {index + 1}.
                          </span>
                          <span>{song}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                </div>
              )}
            </div>

            {event.ticket_url && (
              <a
                href={event.ticket_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors"
              >
                Get Tickets
              </a>
            )}
          </div>

          {/* Attendance Panel */}
          <div className="lg:col-span-1">
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 sticky top-4">
              <h2 className="text-xl font-bold mb-4">Mark Your Attendance</h2>
              
              <div className="space-y-3 mb-4">
                <button
                  onClick={() => handleAttend('going')}
                  disabled={submitting || attendStatus === 'going'}
                  className={`w-full py-3 rounded-lg font-semibold transition-colors ${
                    attendStatus === 'going'
                      ? 'bg-green-600 text-white'
                      : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                  }`}
                >
                  ✓ Going
                </button>
                
                <button
                  onClick={() => handleAttend('maybe')}
                  disabled={submitting || attendStatus === 'maybe'}
                  className={`w-full py-3 rounded-lg font-semibold transition-colors ${
                    attendStatus === 'maybe'
                      ? 'bg-yellow-600 text-white'
                      : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                  }`}
                >
                  ? Maybe
                </button>
                
                <button
                  onClick={() => handleAttend('went')}
                  disabled={submitting || attendStatus === 'went'}
                  className={`w-full py-3 rounded-lg font-semibold transition-colors ${
                    attendStatus === 'went'
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                  }`}
                >
                  ✓ Went
                </button>
              </div>

              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Notes (optional)
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Add notes about this event..."
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                  rows={3}
                />
              </div>

              <div className="border-t border-gray-700 pt-4">
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div>
                    <p className="text-2xl font-bold text-white">{event.going_count}</p>
                    <p className="text-sm text-gray-400">Going</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-white">{event.maybe_count}</p>
                    <p className="text-sm text-gray-400">Maybe</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-white">{event.went_count}</p>
                    <p className="text-sm text-gray-400">Went</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
