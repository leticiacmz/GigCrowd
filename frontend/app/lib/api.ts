import axios from 'axios';
import { getToken } from './auth';


const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000';



const api = axios.create({

  baseURL: API_URL,

  headers: {
    'Content-Type': 'application/json',
  },

});



api.interceptors.request.use(

  (config) => {

    const token = getToken();


    if (token) {

      config.headers.Authorization =
        `Bearer ${token}`;

    }


    return config;

  }

);







export const authAPI = {


  login: async (
    email: string,
    password: string
  ) => {


    const formData =
      new URLSearchParams();


    formData.append(
      'username',
      email
    );


    formData.append(
      'password',
      password
    );


    const response =
      await api.post(

        '/auth/login',

        formData,

        {

          headers: {

            'Content-Type':
              'application/x-www-form-urlencoded',

          },

        }

      );


    return response.data;

  },




  register: async (
    userData: any
  ) => {


    const response =
      await api.post(

        '/auth/register',

        userData

      );


    return response.data;

  },


};









export const userAPI = {


  getMe: async () => {


    const response =
      await api.get(

        '/users/me'

      );


    return response.data;

  },




  getMyStats: async () => {


    const response =
      await api.get(

        '/users/me/stats'

      );


    return response.data;

  },




  getProfile: async (

    username: string

  ) => {


    const response =
      await api.get(

        `/users/profile/${username}`

      );


    return response.data;

  },




  getProfileStats: async (

    username: string

  ) => {


    const response =
      await api.get(

        `/users/profile/${username}/stats`

      );


    return response.data;

  },




  updateMe: async (

    userData: any

  ) => {


    const response =
      await api.put(

        '/users/me',

        userData

      );


    return response.data;

  },


};









export const eventAPI = {


  getEvents: async (

    params?: any

  ) => {


    const response =
      await api.get(

        '/events',

        {
          params,
        }

      );


    return response.data;


  },




  getArtistEvents: async (

    artistSlug: string

  ) => {


    const response =
      await api.get(

        `/events/artist/${artistSlug}`

      );


    return response.data;


  },




  getEvent: async (

    eventId: string

  ) => {


    const response =
      await api.get(

        `/events/${eventId}`

      );


    return response.data;


  },




  attendEvent: async (

    eventId: string,

    status: string,

    notes?: string

  ) => {


    const response =
      await api.post(

        `/events/${eventId}/attend`,

        null,

        {

          params: {

            status,

            notes,

          },

        }

      );


    return response.data;


  },


};









export const postAPI = {


  getPosts: async (

    params?: any

  ) => {


    const response =
      await api.get(

        '/posts',

        {
          params,
        }

      );


    return response.data;


  },




  createPost: async (

    postData: any

  ) => {


    const response =
      await api.post(

        '/posts',

        postData

      );


    return response.data;


  },




  uploadMedia: async (

    file: File

  ) => {


    const formData =
      new FormData();



    formData.append(

      'file',

      file

    );



    const response =
      await api.post(

        '/posts/upload',

        formData,

        {

          headers: {

            'Content-Type':
              'multipart/form-data',

          },

        }

      );


    return response.data;


  },


};









export const feedAPI = {


  getFeed: async (

    params?: any

  ) => {


    const response =
      await api.get(

        '/feed',

        {
          params,
        }

      );


    return response.data;


  },


};









export const followAPI = {


  followUser: async (

    username: string

  ) => {


    const response =
      await api.post(

        `/follows/${username}`

      );


    return response.data;


  },




  unfollowUser: async (

    username: string

  ) => {


    const response =
      await api.delete(

        `/follows/${username}`

      );


    return response.data;


  },




  getStatus: async (

    username: string

  ) => {


    const response =
      await api.get(

        `/follows/${username}/status`

      );


    return response.data;


  },


};









export const artistAPI = {


  getArtists: async (

    params?: any

  ) => {


    const response =
      await api.get(

        '/artists',

        {
          params,
        }

      );


    return response.data;


  },




  searchArtists: async (

    query: string

  ) => {


    const response =
      await api.get(

        '/artists/search',

        {

          params: {

            q: query,

          },

        }

      );


    return response.data;


  },




  getArtist: async (

    artistSlug: string

  ) => {


    const response =
      await api.get(

        `/artists/${artistSlug}`

      );


    return response.data;


  },




  getFollowStatus: async (

    artistSlug: string

  ) => {


    const response =
      await api.get(

        `/artists/${artistSlug}/follow`

      );


    return response.data;


  },




  followArtist: async (

    artistSlug: string

  ) => {


    const response =
      await api.post(

        `/artists/${artistSlug}/follow`

      );


    return response.data;


  },




  unfollowArtist: async (

    artistSlug: string

  ) => {


    const response =
      await api.delete(

        `/artists/${artistSlug}/follow`

      );


    return response.data;


  },


};









export const spotifyAPI = {


  login: async () => {


    const response =
      await api.get(

        '/auth/spotify/login'

      );


    return response.data;


  },




  connect: async (

    tokens: any

  ) => {


    const response =
      await api.post(

        '/auth/spotify/connect',

        tokens

      );


    return response.data;


  },




  getRecommendations: async () => {


    const response =
      await api.get(

        '/auth/spotify/recommendations'

      );


    return response.data;


  },




  disconnect: async () => {


    const response =
      await api.post(

        '/auth/spotify/disconnect'

      );


    return response.data;


  },


};









export default api;