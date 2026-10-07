import axios from 'axios';
import {
  getToken,
  clearStaleAuth,
  getLoginPath,
  sanitizeNext,
} from './auth';
import type { Notification } from '../types/notification';
import type {
  ReviewPayload,
  ShowLog,
  UploadedImage,
} from '../types/review';
import type {
  ProfileArtist,
  ProfileArtistsSeenResponse,
  ProfileEventsPageResponse,
  ProfileEventsResponse,
  ProfileShowCalendarResponse,
  ProfileShowYearsResponse,
} from '../types/profile';

import type {
  EventSearchGenre,
  EventSearchResponse,
} from '../types/eventSearch';

import type {
  ProfileFestival,
  ProfileReview,
  ProfileShowStatus,
} from '../types/profile';

const API_URL =
  typeof window !== 'undefined'
    ? `http://${window.location.hostname}:8000`
    : process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

/** Best-effort locale detection for redirect URLs (first path segment). */
function currentLocale(): string {
  if (typeof window === 'undefined') {
    return 'en';
  }

  const segment = window.location.pathname.split('/')[1];

  return ['en', 'pt-BR', 'es'].includes(segment) ? segment : 'en';
}

/**
 * Attach the bearer token when a session exists.
 *
 * Requests are deliberately NOT redirected here when there is no token:
 * public endpoints must stay reachable while logged out. Authorization is
 * enforced per route/action on the client and by the backend, which remains
 * the security boundary.
 */
api.interceptors.request.use(
  (config) => {
    const token = getToken();

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  }
);

/** Send the user to the localized login, preserving where they were. */
function redirectToLogin() {
  if (typeof window === 'undefined') {
    return;
  }

  const { pathname, search } = window.location;
  const locale = currentLocale();

  const isAuthPage =
    pathname === `/${locale}/login` ||
    pathname === `/${locale}/register`;

  if (isAuthPage) {
    return;
  }

  const next = sanitizeNext(`${pathname}${search}`);

  window.location.href = getLoginPath(locale, next);
}

/** Detail text the backend uses when a user must follow an artist to write. */
const ARTIST_FOLLOW_REQUIRED = 'must follow this artist';

/**
 * True when a 403 means "follow the artist first" rather than "sign in".
 *
 * Only unauthenticated visitors are sent to the login page; a signed-in user
 * who is not following the artist gets the in-place "follow to participate"
 * message instead.
 */
export function isArtistFollowRequired(detail: unknown): boolean {
  return (
    typeof detail === 'string' &&
    detail.toLowerCase().includes(ARTIST_FOLLOW_REQUIRED)
  );
}

// Intercept API responses - handle auth and permission errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;

    // 401 Unauthorized -> session invalid, redirect to login
    if (status === 401) {
      clearStaleAuth();
      redirectToLogin();
      return Promise.reject(error);
    }

    // 403 Forbidden -> a permission problem, not a missing session.
    //
    // Following an artist is required to write in their community, and a
    // signed-in user who does not follow yet must be told so in place. Only a
    // genuinely unauthenticated request is sent to the login page.
    if (status === 403) {
      if (isArtistFollowRequired(error.response?.data?.detail)) {
        return Promise.reject(error);
      }

      clearStaleAuth();
      redirectToLogin();
      return Promise.reject(error);
    }

    return Promise.reject(error);
  }
);

// Export all API modules as named exports
export const artistAPI = {
  getArtists: async (params?: any) => {
    const response = await api.get('/artists', { params });
    return response.data;
  },
  searchArtists: async (query: string) => {
    const response = await api.get('/artists/search', { params: { q: query } });
    return response.data;
  },
  importArtist: async (providerArtistId: string, provider: string = 'songkick', artistData?: any) => {
    const response = await api.post('/artists/import', { provider, provider_artist_id: providerArtistId, artist_data: artistData });
    return response.data;
  },
  getArtist: async (artistSlug: string) => {
    const response = await api.get(`/artists/${artistSlug}`);
    return response.data;
  },
  getFollowStatus: async (artistSlug: string) => {
    const response = await api.get(`/artists/${artistSlug}/follow`);
    return response.data;
  },
  followArtist: async (artistSlug: string) => {
    const response = await api.post(`/artists/${artistSlug}/follow`);
    return response.data;
  },
  unfollowArtist: async (artistSlug: string) => {
    const response = await api.delete(`/artists/${artistSlug}/follow`);
    return response.data;
  },
  getRelatedArtists: async (artistSlug: string) => {
    const response = await api.get(`/artists/${artistSlug}/related`);
    return response.data;
  },
};

export const eventAPI = {
  /**
   * Search the events catalogue.
   *
   * `q` and `genre` compose server-side, inside the one query that also produces
   * the page and the total. Filtering in the browser would make the header count
   * wrong and "next page" jump, because the page would have been sliced before
   * the filter ran.
   *
   * `before`/`beforeId` are opaque: pass back whatever `next_cursor` said and do
   * not interpret it.
   */
  searchEvents: async (options: {
    q?: string;
    genre?: string;
    limit?: number;
    before?: string;
    beforeId?: string;
    includePast?: boolean;
  } = {}) => {
    const response = await api.get('/events', {
      params: {
        q: options.q || undefined,
        genre: options.genre || undefined,
        limit: options.limit,
        before: options.before,
        before_id: options.beforeId,
        include_past: options.includePast || undefined,
      },
    });

    return response.data as EventSearchResponse;
  },

  /**
   * Every genre the catalogue can be filtered by, with how many artists carry it.
   *
   * Read once and held by the caller. The list is derived from artist metadata
   * and does not change as pages load, so re-reading it per keystroke would be a
   * request that always returns the same answer.
   */
  getEventGenres: async () => {
    const response = await api.get('/events/genres');
    return response.data as { genres: EventSearchGenre[] };
  },

  getArtistEvents: async (artistSlug: string) => {
    const response = await api.get(`/events/artist/${artistSlug}`);
    return response.data;
  },
  getAllArtistEvents: async (artistSlug: string) => {
    const response = await api.get(`/artists/${artistSlug}/events/all`);
    return response.data;
  },

  getEvent: async (eventId: string) => {
    const response = await api.get(`/events/${eventId}`);
    return response.data;
  },

  /**
   * The festival behind an event: its identity, every date held for it, and
   * the lineup of the date asked about.
   *
   * One request on purpose. The festival page used to be assembled in the
   * browser from a single event, which meant it could only ever show that one
   * date and whatever lineup happened to be inlined in it - so it showed an
   * empty page for a festival with thirty artists on the bill.
   */
  getFestival: async (eventId: string) => {
    const response = await api.get(`/events/${eventId}/festival`);
    return response.data;
  },
  getAttendance: async (eventId: string) => {
    const response = await api.get(`/events/${eventId}/attendance`);
    return response.data;
  },
};

/**
 * Categories the single feed filter can narrow the timeline to.
 *
 * There is no `social` filter. A follow decides who may see what; it is not
 * something a reader asked to read, so offering it as a card would fill the
 * timeline with relationships nobody chose to publish.
 *
 * `events` is kept as the server-side alias for `attendance`, which is the name
 * a reader recognises for having gone to something.
 */
export type FeedCategory =
  | 'all'
  | 'community'
  | 'reviews'
  | 'attendance'
  | 'events';

export const FEED_CATEGORIES: FeedCategory[] = [
  'all',
  'community',
  'reviews',
  'attendance',
];

export const feedAPI = {
  /**
   * Fetch the unified feed timeline.
   *
   * `category` filters that same timeline; it is the only filter the feed
   * exposes, so there is a single list to reason about.
   */
  getFeed: async (params?: { skip?: number; limit?: number; category?: FeedCategory }) => {
    const response = await api.get('/feed', { params });
    return response.data;
  },
};

export const notificationAPI = {
  /** List the signed-in user's notifications plus the unread count. */
  getNotifications: async (params?: { skip?: number; limit?: number }) => {
    const response = await api.get('/notifications', { params });
    return response.data as {
      notifications: Notification[];
      unread_count: number;
      total: number;
    };
  },
  getUnreadCount: async () => {
    const response = await api.get('/notifications/unread-count');
    return response.data.unread_count as number;
  },
  markAsRead: async (notificationId: string) => {
    const response = await api.post(`/notifications/${notificationId}/read`);
    return response.data;
  },
  markAllAsRead: async () => {
    const response = await api.post('/notifications/read-all');
    return response.data;
  },
};

export const postAPI = {
  getPosts: async (params?: any) => {
    const response = await api.get('/posts', { params });
    return response.data;
  },
  createPost: async (postData: any) => {
    const response = await api.post('/posts', postData);
    return response.data;
  },
  uploadMedia: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/posts/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
};

export const followAPI = {
  followUser: async (username: string) => {
    const response = await api.post(`/follows/${username}`);
    return response.data;
  },
  unfollowUser: async (username: string) => {
    const response = await api.delete(`/follows/${username}`);
    return response.data;
  },
  getStatus: async (username: string) => {
    const response = await api.get(`/follows/${username}/status`);
    return response.data;
  },
};

export const communityPostAPI = {
  getPosts: async (artistSlug: string, params?: any) => {
    const response = await api.get(`/artists/${artistSlug}/community/posts`, { params });
    return response.data;
  },

  createPost: async (artistSlug: string, postData: {
    content: string;
    image_url?: string;
  }) => {
    const response = await api.post(`/artists/${artistSlug}/community/posts`, postData);
    return response.data;
  },

  likePost: async (artistSlug: string, postId: string) => {
    const response = await api.post(`/artists/${artistSlug}/community/posts/${postId}/like`);
    return response.data;
  },

  unlikePost: async (artistSlug: string, postId: string) => {
    const response = await api.delete(`/artists/${artistSlug}/community/posts/${postId}/like`);
    return response.data;
  },

  deletePost: async (artistSlug: string, postId: string) => {
    const response = await api.delete(`/artists/${artistSlug}/community/posts/${postId}`);
    return response.data;
  },
};

export const commentAPI = {
  getComments: async (artistSlug: string, postId: string, params?: any) => {
    const response = await api.get(`/artists/${artistSlug}/community/posts/${postId}/comments`, { params });
    return response.data;
  },
  getReplies: async (artistSlug: string, commentId: string, params?: any) => {
    const response = await api.get(`/artists/${artistSlug}/community/comments/${commentId}/replies`, { params });
    return response.data;
  },
  createComment: async (artistSlug: string, data: {
    post_id: string;
    content: string;
    parent_comment_id?: string;
  }) => {
    const response = await api.post(`/artists/${artistSlug}/community/comments`, data);
    return response.data;
  },
  updateComment: async (artistSlug: string, commentId: string, data: {
    content: string;
  }) => {
    const response = await api.put(`/artists/${artistSlug}/community/comments/${commentId}`, data);
    return response.data;
  },
  deleteComment: async (artistSlug: string, commentId: string) => {
    const response = await api.delete(`/artists/${artistSlug}/community/comments/${commentId}`);
    return response.data;
  },
};

export const showLogAPI = {
  /**
   * The signed-in user's log for one event, or `null` when they have none.
   *
   * A missing log is an ordinary state rather than an error, so a 404 is
   * resolved to `null` instead of rejecting and forcing every caller to know it.
   */
  get: async (eventId: string): Promise<ShowLog | null> => {
    try {
      const response = await api.get(`/show-logs/${eventId}`);
      return response.data as ShowLog;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        return null;
      }

      throw error;
    }
  },
  create: async (data: {
    event_id: string;
    status: ShowLog['status'];
    rating?: number;
    review?: string;
  }): Promise<ShowLog> => {
    const response = await api.post('/show-logs', data);
    return response.data as ShowLog;
  },
  delete: async (eventId: string) => {
    const response = await api.delete(`/show-logs/${eventId}`);
    return response.data;
  },
  /**
   * Write or replace the review on a show log.
   *
   * A review needs a rating plus something to say: text, a photo, or both. A
   * bare star rating is not a review, so the dialog asks for one of the two.
   */
  saveReview: async (
    eventId: string,
    data: ReviewPayload,
  ): Promise<ShowLog> => {
    const response = await api.put(`/show-logs/${eventId}/review`, data);
    return response.data as ShowLog;
  },
  deleteReview: async (eventId: string): Promise<ShowLog> => {
    const response = await api.delete(`/show-logs/${eventId}/review`);
    return response.data as ShowLog;
  },
};

export const spotifyAPI = {
  login: async () => {
    const response = await api.get('/auth/spotify/login');
    return response.data;
  },
  connect: async (tokens: any) => {
    const response = await api.post('/auth/spotify/connect', tokens);
    return response.data;
  },
  getRecommendations: async () => {
    const response = await api.get('/auth/spotify/recommendations');
    return response.data;
  },
  disconnect: async () => {
    const response = await api.post('/auth/spotify/disconnect');
    return response.data;
  },
};

export const userAPI = {
  getMe: async () => {
    const response = await api.get('/users/me');
    return response.data;
  },
  getMyStats: async () => {
    const response = await api.get('/users/me/stats');
    return response.data;
  },
  getProfile: async (username: string) => {
    const response = await api.get(`/users/profile/${username}`);
    return response.data;
  },
  getProfileStats: async (username: string) => {
    const response = await api.get(`/users/profile/${username}/stats`);
    return response.data;
  },
  /**
   * Public social graph of a profile.
   * `direction` picks between the people who follow the user and the people
   * the user follows, so one list component can render both.
   */
  getConnections: async (
    username: string,
    direction: 'followers' | 'following' = 'followers'
  ) => {
    const response = await api.get(
      `/users/profile/${username}/connections`,
      { params: { direction } }
    );
    return response.data as {
      username: string;
      direction: 'followers' | 'following';
      users: {
        id: string;
        username: string;
        full_name?: string | null;
        avatar_url?: string | null;
      }[];
    };
  },
  updateMe: async (userData: {
    full_name?: string;
    bio?: string;
    location?: string;
  }) => {
    const response = await api.put('/users/me', userData);
    return response.data;
  },

  /**
   * The shows a user logged, in one of the three states a show can be in.
   *
   * `status` selects the state - `attended`, `want-to-go` or `maybe` - and
   * `all` returns every logged show. It defaults to `attended`, which is what
   * the profile has always opened with.
   *
   * Every response carries the count for all three states, so the breakdown is
   * drawn from the same rows as the list under it and one request is enough to
   * fill the whole section.
   */
  getProfileEvents: async (
    username: string,
    limit?: number,
    status: ProfileShowStatus | 'all' = 'attended',
    skip?: number
  ) => {
    const response = await api.get(`/users/profile/${username}/events`, {
      params: {
        ...(limit ? { limit } : {}),
        ...(skip ? { skip } : {}),
        status,
      },
    });
    return response.data as ProfileEventsResponse;
  },

  /**
   * One page of a user's show history, addressed by cursor.
   *
   * The diary is read by scrolling into the past, so paging by position would make
   * every page re-read the pages before it. The cursor comes back from the server
   * and is passed straight back; nothing here interprets it.
   */
  getProfileEventsPage: async (
    username: string,
    options: {
      status?: ProfileShowStatus | 'all';
      limit?: number;
      before?: string;
      beforeId?: string;
    } = {}
  ) => {
    const response = await api.get(
      `/users/profile/${username}/events/page`,
      {
        params: {
          ...(options.status ? { status: options.status } : {}),
          ...(options.limit ? { limit: options.limit } : {}),
          ...(options.before ? { before: options.before } : {}),
          ...(options.beforeId ? { before_id: options.beforeId } : {}),
        },
      }
    );
    return response.data as ProfileEventsPageResponse;
  },

  /**
   * The days in one month on which this user says they went to a show.
   *
   * Only shows logged as `went` mark a day. Bounded to the month, so opening the
   * calendar costs one month of history rather than all of it.
   */
  getProfileShowCalendar: async (
    username: string,
    year: number,
    month: number
  ) => {
    const response = await api.get(
      `/users/profile/${username}/shows/calendar`,
      { params: { year, month } }
    );
    return response.data as ProfileShowCalendarResponse;
  },

  /**
   * The years this user says they went to a show, newest first.
   *
   * Read once per profile and reused by the calendar's year selector, so reaching
   * a year with shows in it costs one small request instead of a walk through
   * the months. The current year is always present even when empty, so the
   * selector can offer the year somebody opened the calendar in.
   */
  getProfileShowYears: async (username: string) => {
    const response = await api.get(
      `/users/profile/${username}/shows/years`
    );
    return response.data as ProfileShowYearsResponse;
  },

  /** The reviews a user wrote, most recently written first. */
  getProfileReviews: async (username: string, limit?: number) => {
    const response = await api.get(`/users/profile/${username}/reviews`, {
      params: limit ? { limit } : undefined,
    });
    return response.data as {
      username: string;
      reviews: ProfileReview[];
      total: number;
    };
  },

  /**
   * The festivals a user has been to.
   *
   * Editions of the same festival collapse into one row, so the count is the
   * number of festivals and not the number of tickets.
   */
  getProfileFestivals: async (username: string) => {
    const response = await api.get(`/users/profile/${username}/festivals`);
    return response.data as {
      username: string;
      festivals: ProfileFestival[];
      total: number;
    };
  },

  /** The artists a user follows, which are the communities they belong to. */
  getProfileArtists: async (username: string, limit?: number) => {
    const response = await api.get(`/users/profile/${username}/artists`, {
      params: limit ? { limit } : undefined,
    });
    return response.data as {
      username: string;
      artists: ProfileArtist[];
      total: number;
    };
  },

  /**
   * The artists a user has actually been to a show of, most seen first.
   *
   * One request, and the counts come with it. Reading this as "fetch the
   * attended events, then fetch each artist, then count them one at a time"
   * would mean a profile with fifty shows makes a hundred requests.
   */
  getProfileArtistsSeen: async (username: string, limit?: number) => {
    const response = await api.get(
      `/users/profile/${username}/artists-seen`,
      { params: limit ? { limit } : undefined }
    );
    return response.data as ProfileArtistsSeenResponse;
  },
};

/**
 * Image upload, used by anything that attaches a photo.
 *
 * One endpoint for every image the product accepts: the file is posted to the
 * backend, which validates it, stores it and returns the public URL, so the
 * Cloudinary secret never reaches the browser.
 */
export const mediaAPI = {
  uploadImage: async (file: File) => {
    const formData = new FormData();
    formData.append('image', file);

    const response = await api.post('/media/images', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });

    return response.data as UploadedImage;
  },
};

export const authAPI = {
  login: async (email: string, password: string) => {
    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);
    const response = await api.post('/auth/login', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
    return response.data;
  },
  register: async (userData: any) => {
    const response = await api.post('/auth/register', userData);
    return response.data;
  },
};

export default api;