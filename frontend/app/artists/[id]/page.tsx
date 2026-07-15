'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';

import { artistAPI } from '../../lib/api';


interface ArtistProfile {
  id?: string;

  provider: string;

  provider_artist_id: string;

  name: string;

  followers?: number;

  image?: string;

  genres: string[];

  popularity?: number;

  verified: boolean;

  is_imported: boolean;

  slug?: string;
}



export default function ArtistProfilePage() {

  const params = useParams();

  const router = useRouter();


  const artistId = params.id as string;



  const [artist, setArtist] = useState<ArtistProfile | null>(null);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState('');




  useEffect(() => {

    const token = localStorage.getItem('token');


    if (!token) {

      router.push('/login');

      return;

    }


    loadArtist();


  }, [artistId]);





  const loadArtist = async () => {

    try {

      setLoading(true);


      const data = await artistAPI.getArtist(artistId);


      setArtist(data);


    } catch (error) {


      console.error('Failed to load artist:', error);


      setError('Could not load artist profile.');


    } finally {


      setLoading(false);

    }

  };





  if (loading) {

    return (

      <div className="min-h-screen flex items-center justify-center">

        <p className="text-gray-400">
          Loading artist...
        </p>

      </div>

    );

  }






  if (error || !artist) {

    return (

      <div className="min-h-screen flex flex-col items-center justify-center gap-4">


        <p className="text-red-400">

          {error || 'Artist not found.'}

        </p>



        <Link
          href="/artists"
          className="text-purple-400 hover:text-purple-300"
        >

          Back to artists

        </Link>


      </div>

    );

  }







  return (

    <div className="min-h-screen">



      <header className="border-b border-gray-800 px-4 py-4">


        <div className="max-w-6xl mx-auto flex justify-between items-center">


          <Link

            href="/feed"

            className="text-2xl font-bold bg-gradient-to-r from-purple-500 to-pink-500 bg-clip-text text-transparent"

          >

            GigCrowd

          </Link>




          <Link

            href="/artists"

            className="text-gray-400 hover:text-white"

          >

            Back to artists

          </Link>



        </div>


      </header>







      <main className="max-w-4xl mx-auto px-4 py-10">



        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">





          {artist.image && (

            <img

              src={artist.image}

              alt={artist.name}

              className="w-full h-80 object-cover"

            />

          )}






          <div className="p-8">





            <div className="flex items-center gap-3 mb-4">


              <h1 className="text-4xl font-bold text-white">

                {artist.name}

              </h1>




              {artist.verified && (

                <span className="text-purple-400 text-sm">

                  ✓ Verified

                </span>

              )}



            </div>







            {artist.genres.length > 0 && (

              <div className="mb-6">


                <h2 className="text-sm text-gray-400 mb-2">

                  Genres

                </h2>



                <div className="flex flex-wrap gap-2">


                  {artist.genres.map((genre) => (

                    <span

                      key={genre}

                      className="px-3 py-1 bg-gray-800 rounded-full text-sm text-gray-300"

                    >

                      {genre}

                    </span>

                  ))}



                </div>


              </div>

            )}








            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">



              {artist.followers !== undefined && (

                <div className="bg-gray-800 rounded-lg p-4">


                  <p className="text-gray-400 text-sm">

                    Followers

                  </p>


                  <p className="text-white text-xl font-semibold">

                    {artist.followers.toLocaleString()}

                  </p>


                </div>

              )}







              {artist.popularity !== undefined && (

                <div className="bg-gray-800 rounded-lg p-4">


                  <p className="text-gray-400 text-sm">

                    Popularity

                  </p>


                  <p className="text-white text-xl font-semibold">

                    {artist.popularity}

                  </p>


                </div>

              )}







              <div className="bg-gray-800 rounded-lg p-4">


                <p className="text-gray-400 text-sm">

                  Source

                </p>


                <p className="text-white text-xl font-semibold capitalize">

                  {artist.provider}

                </p>


              </div>



            </div>






            {artist.is_imported && (

              <p className="mt-6 text-sm text-gray-500">

                Imported from external provider

              </p>

            )}





          </div>


        </div>



      </main>


    </div>

  );

}