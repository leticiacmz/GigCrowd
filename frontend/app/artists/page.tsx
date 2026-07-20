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


    const token =
      localStorage.getItem('token');



    if (!token) {

      router.push('/login');

      return;

    }



    loadArtists();

    loadCurrentUser();



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



      <header
        className="
          border-b
          border-gray-800
          px-4
          py-4
        "
      >


        <div
          className="
            max-w-6xl
            mx-auto
            flex
            items-center
            justify-between
          "
        >


          <Link

            href="/feed"

            className="
              text-2xl
              font-bold
              bg-gradient-to-r
              from-purple-500
              to-pink-500
              bg-clip-text
              text-transparent
            "

          >

            GigCrowd

          </Link>





          <nav
            className="
              flex
              gap-4
            "
          >


            <Link

              href="/feed"

              className="
                text-gray-400
                hover:text-white
              "

            >

              Feed

            </Link>





            <Link

              href="/events"

              className="
                text-gray-400
                hover:text-white
              "

            >

              Events

            </Link>





            <Link

              href={
                currentUser
                  ? `/profile/${currentUser.username}`
                  : '/login'
              }

              className="
                text-gray-400
                hover:text-white
              "

            >

              Profile

            </Link>



          </nav>



        </div>


      </header>









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
            text-3xl
            font-bold
            mb-8
          "

        >

          Artists


        </h1>









        {
          error && (


            <div

              className="
                mb-6
                p-4
                rounded
                bg-red-900
                text-red-200
              "

            >

              {error}


            </div>


          )
        }









        {
          loading ? (


            <div

              className="
                grid
                grid-cols-1
                md:grid-cols-3
                gap-6
              "

            >


              {
                Array.from(
                  {
                    length: 6,
                  }
                ).map(
                  (
                    _,
                    index
                  ) => (


                    <div

                      key={index}

                      className="
                        bg-gray-900
                        rounded-lg
                        p-4
                        animate-pulse
                      "

                    >

                      <div
                        className="
                          h-48
                          bg-gray-800
                          rounded
                          mb-4
                        "
                      />


                      <div
                        className="
                          h-5
                          bg-gray-800
                          rounded
                          w-3/4
                        "
                      />


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
                          text-2xl
                          font-bold
                          mb-4
                          text-purple-400
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


                        {
                          groupedArtists[letter]
                            .map(
                              (
                                artist
                              ) => (


                                <Link


                                  key={
                                    artist.slug ||
                                    artist.provider_artist_id
                                  }


                                  href={
                                    `/artists/${artist.slug}`
                                  }


                                  className="
                                    bg-gray-900
                                    border
                                    border-gray-800
                                    rounded-lg
                                    overflow-hidden
                                    hover:border-purple-500
                                    transition
                                  "


                                >




                                  {
                                    artist.image ? (


                                      <img

                                        src={
                                          artist.image
                                        }

                                        alt={
                                          artist.name
                                        }

                                        className="
                                          w-full
                                          h-48
                                          object-cover
                                        "

                                      />


                                    ) : (


                                      <div

                                        className="
                                          h-48
                                          flex
                                          items-center
                                          justify-center
                                          bg-gray-800
                                          text-5xl
                                        "

                                      >

                                        🎵


                                      </div>


                                    )

                                  }





                                  <div className="p-4">


                                    <h3

                                      className="
                                        text-white
                                        font-semibold
                                      "

                                    >

                                      {artist.name}


                                    </h3>





                                    {
                                      artist.genres?.length > 0 && (


                                        <p

                                          className="
                                            text-sm
                                            text-gray-400
                                            mt-2
                                          "

                                        >

                                          {
                                            artist.genres.join(
                                              ', '
                                            )
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