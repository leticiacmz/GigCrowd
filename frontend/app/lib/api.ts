import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});


export const authAPI = {
  login: async (email: string, password: string) => {
    const response = await api.post('/auth/login', null, {
      params: { email, password },
    });

    return response.data;
  },

  register: async (userData: any) => {
    const response = await api.post('/auth/register', userData);

    return response.data;
  },
};


export const userAPI = {
  getMe: async () => {
    const response = await api.get('/users/me');

    return response.data;
  },

  updateMe: async (userData: any) => {
    const response = await api.put('/users/me', userData);

    return response.data;
  },

  getUser: async (userId: string) => {
    const response = await api.get(`/users/${userId}`);

    return response.data;
  },
};


export const eventAPI = {
  getEvents: async (params?: any) => {
    const response = await api.get('/events', {
      params,
    });

    return response.data;
  },

  getEvent: async (eventId: string) => {
    const response = await api.get(`/events/${eventId}`);

    return response.data;
  },

  attendEvent: async (
    eventId: string,
    status: string,
    notes?: string
  ) => {
    const response = await api.post(`/events/${eventId}/attend`, null, {
      params: {
        status,
        notes,
      },
    });

    return response.data;
  },

  searchExternal: async (
    query: string,
    eventType?: 'past' | 'future',
    specificDate?: string,
    startDate?: string,
    endDate?: string
  ) => {
    const params: any = {
      query,
    };

    if (eventType) {
      params.event_type = eventType;
    }

    if (specificDate) {
      params.specific_date = specificDate;
    }

    if (startDate) {
      params.start_date = startDate;
    }

    if (endDate) {
      params.end_date = endDate;
    }

    const response = await api.get('/events/search/external', {
      params,
    });

    return response.data;
  },
};


export const postAPI = {
  getPosts: async (params?: any) => {
    const response = await api.get('/posts', {
      params,
    });

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


export const feedAPI = {
  getFeed: async (params?: any) => {
    const response = await api.get('/feed', {
      params,
    });

    return response.data;
  },
};


export const followAPI = {
  followUser: async (followingId: string) => {
    const response = await api.post('/follows', {
      following_id: followingId,
    });

    return response.data;
  },

  unfollowUser: async (followingId: string) => {
    const response = await api.delete(`/follows/${followingId}`);

    return response.data;
  },
};


export const artistAPI = {
  getArtists: async (params?: any) => {
    const response = await api.get('/artists', {
      params,
    });

    return response.data;
  },

  getArtist: async (artistId: string) => {
    const response = await api.get(`/artists/${artistId}`);

    return response.data;
  },

  searchArtists: async (query: string) => {
    const response = await api.get('/artists/search', {
      params: {
        q: query,
      },
    });

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


export default api;