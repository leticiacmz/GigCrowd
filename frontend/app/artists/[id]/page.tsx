'use client';

import {
  useEffect,
  useState,
} from 'react';

import {
  useParams,
  useRouter,
} from 'next/navigation';

import Link from 'next/link';

import {
  artistAPI,
} from '../../lib/api';


interface ArtistProfile {

  id: string;

  slug: string;

  name: string;

  image?: string;

  genres: string[];

  events: {

    upcoming: number;

    total: number;

  };

}



interface ArtistEvent {

  id: string;

  title: string;

  starts_at: string;

  ticket_url?: string;

  venue?: {

    name?: string;

    city?: string;

    country?: string;

  };

}



export default function ArtistProfilePage() {


  const params = useParams();

  const router = useRouter();


  const artistSlug = params.id as string;



  const [
    artist,
    setArtist,
  ] = useState<ArtistProfile | null>(null);



  const [
    events,
    setEvents,
  ] = useState<ArtistEvent[]>([]);



  const [
    loading,
    setLoading,
  ] = useState(true);



  const [
    error,
    setError,
  ] = useState('');





  useEffect(() => {


    const token = localStorage.getItem(
      'token'
    );


    if (!token) {

      router.push('/login');

      return;

    }


    loadArtist();


  }, [artistSlug]);





  async function loadArtist() {


    try {


      setLoading(true);

      setError('');



      const [
        artistData,
        eventsData,
      ] = await Promise.all([

        artistAPI.getArtist(
          artistSlug
        ),

        artistAPI.getArtistEvents(
          artistSlug
        ),

      ]);



      setArtist(
        artistData
      );


      setEvents(
        eventsData
      );



    } catch (error) {


      console.error(
        'Failed to load artist:',
        error
      );


      setError(
        'Could not load artist profile.'
      );


    } finally {


      setLoading(false);

    }


  }





  function formatDate(
    date: string
  ) {


    return new Date(
      date
    ).toLocaleDateString(
      'en-US',
      {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      }
    );


  }







  if (loading) {


    return (

      <div className="
        min-h-screen
        flex
        items-center
        justify-center
      ">

        <p className="
          text-gray-400
        ">

          Loading artist...

        </p>


      </div>

    );


  }






  if (error || !artist) {


    return (

      <div className="
        min-h-screen
        flex
        flex-col
        items-center
        justify-center
        gap-4
      ">


        <p className="
          text-red-400
        ">

          {error || 'Artist not found.'}

        </p>



        <Link

          href="/artists"

          className="
            text-purple-400
            hover:text-purple-300
          "

        >

          Back to artists

        </Link>


      </div>

    );


  }








  return (


    <div className="
      min-h-screen
    ">



      <header className="
        border-b
        border-gray-800
        px-4
        py-4
      ">


        <div className="
          max-w-6xl
          mx-auto
          flex
          justify-between
          items-center
        ">


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




          <Link

            href="/artists"

            className="
              text-gray-400
              hover:text-white
            "

          >

            Back to artists

          </Link>


        </div>


      </header>







      <main className="
        max-w-5xl
        mx-auto
        px-4
        py-10
      ">





        <section className="
          bg-gray-900
          border
          border-gray-800
          rounded-xl
          overflow-hidden
        ">



          {
            artist.image && (

              <img

                src={artist.image}

                alt={artist.name}

                className="
                  w-full
                  h-80
                  object-cover
                "

              />

            )
          }





          <div className="
            p-8
          ">



            <h1 className="
              text-4xl
              font-bold
              text-white
              mb-4
            ">

              {artist.name}

            </h1>





            {
              artist.genres.length > 0 && (

                <div className="
                  flex
                  flex-wrap
                  gap-2
                  mb-6
                ">


                  {
                    artist.genres.map(
                      genre => (

                        <span

                          key={genre}

                          className="
                            px-3
                            py-1
                            bg-gray-800
                            rounded-full
                            text-sm
                            text-gray-300
                          "

                        >

                          {genre}

                        </span>

                      )
                    )
                  }


                </div>

              )
            }






            <div className="
              grid
              grid-cols-1
              md:grid-cols-2
              gap-4
            ">



              <div className="
                bg-gray-800
                rounded-lg
                p-5
              ">


                <p className="
                  text-gray-400
                  text-sm
                ">

                  Upcoming Shows

                </p>


                <p className="
                  text-white
                  text-3xl
                  font-bold
                ">

                  {artist.events.upcoming}

                </p>


              </div>





              <div className="
                bg-gray-800
                rounded-lg
                p-5
              ">


                <p className="
                  text-gray-400
                  text-sm
                ">

                  Total Shows

                </p>


                <p className="
                  text-white
                  text-3xl
                  font-bold
                ">

                  {artist.events.total}

                </p>


              </div>


            </div>



          </div>



        </section>









        <section className="
          mt-10
        ">


          <h2 className="
            text-2xl
            font-bold
            text-white
            mb-6
          ">

            Upcoming Events

          </h2>






          {
            events.length === 0 ? (

              <p className="
                text-gray-400
              ">

                No upcoming events found.

              </p>


            ) : (


              <div className="
                space-y-4
              ">


                {
                  events.map(
                    event => (


                      <div

                        key={event.id}

                        className="
                          bg-gray-900
                          border
                          border-gray-800
                          rounded-lg
                          p-5
                        "

                      >



                        <h3 className="
                          text-xl
                          font-semibold
                          text-white
                        ">

                          {event.title}

                        </h3>




                        <p className="
                          text-gray-400
                          mt-2
                        ">

                          {formatDate(
                            event.starts_at
                          )}

                        </p>





                        {
                          event.venue && (

                            <p className="
                              text-gray-500
                              mt-1
                            ">


                              {event.venue.name}

                              {
                                event.venue.city &&
                                ` - ${event.venue.city}`
                              }

                              {
                                event.venue.country &&
                                `, ${event.venue.country}`
                              }


                            </p>

                          )
                        }





                        {
                          event.ticket_url && (

                            <a

                              href={event.ticket_url}

                              target="_blank"

                              rel="noopener noreferrer"

                              className="
                                inline-block
                                mt-4
                                text-purple-400
                                hover:text-purple-300
                              "

                            >

                              Buy Ticket →

                            </a>

                          )
                        }




                      </div>


                    )
                  )
                }


              </div>


            )
          }



        </section>





      </main>



    </div>


  );


}