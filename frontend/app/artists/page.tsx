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
  userAPI,
} from '../lib/api';

import {
  Artist,
} from '../types/artist';

import ArtistCard from '../../components/ArtistCard';
import LoadingState from '../../components/LoadingState';
import EmptyState from '../../components/EmptyState';
import Card from '../../components/ui/Card';



export default function ArtistsPage() {


  const router = useRouter();



  const [
    artists,
    setArtists,
  ] = useState<Artist[]>([]);



  const [
    currentUser,
    setCurrentUser,
  ] = useState<any>(null);



  const [
    loading,
    setLoading,
  ] = useState(true);



  const [
    error,
    setError,
  ] = useState('');


  useEffect(() => {


    loadArtists();

    const token =
    localStorage.getItem('token');

    if(token){
      loadCurrentUser();
    }



  }, [router]);









  async function loadCurrentUser() {


    try {


      const user =
        await userAPI.getMe();



      setCurrentUser(
        user
      );


    } catch(error) {


      console.error(
        'Failed to load user:',
        error
      );


    }


  }









  async function loadArtists() {


    try {


      setLoading(true);

      setError('');



      const data =
        await artistAPI.getArtists();



      const sortedArtists =
        data.sort(
          (
            a: Artist,
            b: Artist
          ) =>
            a.name.localeCompare(
              b.name
            )
        );



      setArtists(
        sortedArtists
      );



    } catch(error) {


      console.error(
        'Failed to load artists:',
        error
      );



      setError(
        'Could not load artists.'
      );



    } finally {


      setLoading(false);


    }


  }









  function groupArtistsByLetter(
    artists: Artist[]
  ) {


    return artists.reduce(
      (
        groups,
        artist
      ) => {


        const letter =
          artist.name
            .charAt(0)
            .toUpperCase();



        if (!groups[letter]) {

          groups[letter] = [];

        }



        groups[letter].push(
          artist
        );



        return groups;


      },
      {} as Record<string, Artist[]>
    );


  }







  const groupedArtists =
    groupArtistsByLetter(
      artists
    );



  const letters =
    Object.keys(
      groupedArtists
    ).sort();









  return (


    <div className="min-h-screen">



      <main
        className="
          max-w-6xl
          mx-auto
          px-4
          py-8
        "
      >



        <h1

          className="
            text-[28px]
            font-bold
            mb-8
          "

        >

          Artists


        </h1>









        {
          error && (


            <Card className="mb-6 p-4 bg-red-900/20 border-red-500 text-red-300">

              {error}

            </Card>


          )
        }









        {
          loading ? (
            <LoadingState message="Loading artists..." />
          ) : artists.length === 0 ? (
            <EmptyState
              icon="🎵"
              title="No artists found"
              description="Start following artists to see them here!"
            />



          ) : (


            <div className="space-y-10">



              {
                letters.map(
                  (
                    letter
                  ) => (


                    <section

                      key={letter}

                    >


                      <h2

                        className="
                          text-[24px]
                          font-bold
                          mb-4
                          text-secondary
                        "

                      >

                        {letter}


                      </h2>





                      <div

                        className="
                          grid
                          grid-cols-1
                          md:grid-cols-2
                          lg:grid-cols-3
                          gap-6
                        "

                      >


                        {groupedArtists[letter].map((artist) => (
                          <ArtistCard
                            key={artist.slug || artist.provider_artist_id}
                            artist={artist}
                          />
                        ))}




                      </div>



                    </section>


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