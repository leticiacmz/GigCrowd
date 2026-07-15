'use client';

import {
  useEffect,
  useState,
} from 'react';

import {
  useRouter,
} from 'next/navigation';

import Link from 'next/link';

import {
  artistAPI,
} from '../lib/api';

import {
  Artist,
} from '../types/artist';


export default function ArtistsPage() {


  const router = useRouter();


  const [
    artists,
    setArtists,
  ] = useState<Artist[]>([]);



  const [
    searchQuery,
    setSearchQuery,
  ] = useState('');



  const [
    loading,
    setLoading,
  ] = useState(true);



  const [
    searching,
    setSearching,
  ] = useState(false);



  const [
    error,
    setError,
  ] = useState('');





  useEffect(() => {


    const token =
      localStorage.getItem('token');



    if (!token) {

      router.push('/login');

      return;

    }



    loadArtists();



  }, [router]);






  async function loadArtists() {


    try {


      setLoading(true);

      setError('');



      const data =
        await artistAPI.getArtists();



      setArtists(data);



    } catch (error) {


      console.error(
        'Failed to load artists:',
        error,
      );



      setError(
        'Could not load artists.',
      );



    } finally {


      setLoading(false);


    }


  }








  async function handleSearch(
    e: React.FormEvent,
  ) {


    e.preventDefault();




    if (!searchQuery.trim()) {


      loadArtists();

      return;


    }




    try {


      setSearching(true);

      setError('');



      const data =
        await artistAPI.searchArtists(
          searchQuery,
        );



      setArtists(data);



    } catch (error) {


      console.error(
        'Failed to search artists:',
        error,
      );



      setError(
        'Could not search artists.',
      );



    } finally {


      setSearching(false);


    }


  }







  return (


    <div className="min-h-screen">



      <header className="border-b border-gray-800 px-4 py-4">


        <div className="max-w-6xl mx-auto flex items-center justify-between">


          <Link

            href="/feed"

            className="text-2xl font-bold bg-gradient-to-r from-purple-500 to-pink-500 bg-clip-text text-transparent"

          >

            GigCrowd

          </Link>





          <nav className="flex gap-4">


            <Link
              href="/feed"
              className="text-gray-400 hover:text-white"
            >

              Feed

            </Link>




            <Link
              href="/events"
              className="text-gray-400 hover:text-white"
            >

              Events

            </Link>




            <Link
              href="/profile"
              className="text-gray-400 hover:text-white"
            >

              Profile

            </Link>



          </nav>



        </div>


      </header>








      <main className="max-w-6xl mx-auto px-4 py-8">



        <h1 className="text-3xl font-bold mb-6">

          Discover Artists

        </h1>







        <form
          onSubmit={handleSearch}
          className="mb-8"
        >


          <div className="flex gap-4">



            <input

              value={searchQuery}

              onChange={
                (e) =>
                  setSearchQuery(
                    e.target.value,
                  )
              }


              placeholder="Search artists..."


              className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white"

            />





            <button

              disabled={searching}

              className="px-6 py-3 bg-purple-600 rounded-lg text-white disabled:opacity-50"

            >


              {
                searching
                  ? 'Searching...'
                  : 'Search'
              }


            </button>




          </div>


        </form>









        {
          error && (

            <div className="mb-6 p-4 rounded bg-red-900 text-red-200">

              {error}

            </div>

          )
        }








        {
          loading ? (


            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">


              {
                Array.from(
                  {
                    length: 6,
                  }
                ).map(
                  (_, index) => (

                    <div

                      key={index}

                      className="bg-gray-900 rounded-lg p-4 animate-pulse"

                    >

                      <div className="h-48 bg-gray-800 rounded mb-4" />

                      <div className="h-5 bg-gray-800 rounded w-3/4" />


                    </div>


                  )
                )
              }


            </div>



          ) : artists.length === 0 ? (


            <div className="text-gray-400">

              No artists found.

            </div>



          ) : (



            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">



              {
                artists.map(
                  (artist) => (


                    <Link


                      key={
                        artist.slug ||
                        artist.provider_artist_id
                      }


                      href={
                        `/artists/${artist.slug}`
                      }



                      className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden hover:border-purple-500 transition"



                    >




                      {
                        artist.image ? (


                          <img

                            src={artist.image}

                            alt={artist.name}

                            className="w-full h-48 object-cover"

                          />


                        ) : (


                          <div className="h-48 flex items-center justify-center bg-gray-800 text-5xl">

                            🎵

                          </div>


                        )

                      }







                      <div className="p-4">



                        <h3 className="text-white font-semibold">

                          {artist.name}

                        </h3>





                        {
                          artist.genres?.length > 0 && (


                            <p className="text-sm text-gray-400 mt-2">

                              {
                                artist.genres.join(', ')
                              }


                            </p>


                          )
                        }



                      </div>




                    </Link>



                  )
                )
              }



            </div>



          )
        }




      </main>



    </div>



  );


}