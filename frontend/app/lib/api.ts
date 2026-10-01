import axios from 'axios';
import {
  getToken,
  clearStaleAuth,
  getLoginPath,
  sanitizeNext,
} from './auth';

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000';

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

// Intercept API responses - an authenticated endpoint rejected the session
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;

    // 401 Unauthorized / 403 Forbidden -> the session is no longer valid.
    if (status === 401 || status === 403) {
      clearStaleAuth();
      redirectToLogin();
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
  getEvents: async (params?: any) => {
    const response = await api.get('/events', { params });
    return response.data;
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
  getAttendance: async (eventId: string) => {
    const response = await api.get(`/events/${eventId}/attendance`);
    return response.data;
  },
};

export const feedAPI = {
  getFeed: async (params?: any) => {
    const response = await api.get('/feed', { params });
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
  get: async (eventId: string) => {
    const response = await api.get(`/show-logs/${eventId}`);
    return response.data;
  },
  create: async (data: any) => {
    const response = await api.post('/show-logs', data);
    return response.data;
  },
  update: async (eventId: string, data: {
    review?: string;
    rating?: number;
  }) => {
    const response = await api.put(`/show-logs/${eventId}`, data);
    return response.data;
  },
  delete: async (eventId: string) => {
    const response = await api.delete(`/show-logs/${eventId}`);
    return response.data;
  },
  deleteReview: async (eventId: string) => {
    const response = await api.delete(`/show-logs/${eventId}/review`);
    return response.data;
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
  updateMe: async (userData) => {
    const response = await api.put('/users/me', userData);
    return response.data;
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