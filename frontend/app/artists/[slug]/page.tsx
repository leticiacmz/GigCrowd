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
  eventAPI,
} from '../../lib/api';
import Button from '../../../components/ui/Button';
import Card from '../../../components/ui/Card';
import Badge from '../../../components/ui/Badge';
import LoadingState from '../../../components/LoadingState';







interface ArtistProfile {


  id?: string;


  slug?: string;


  name: string;


  image?: string;


  genres: string[];


  events?: {

    upcoming: number;

    total: number;

  };


}





interface ArtistEvent {

  id: string;

  title: string;

  starts_at: string;

  ticket_url?: string | null;

  free?: boolean | null;

  sold_out?: boolean | null;

  venue?: {

    id?: string | null;

    slug?: string | null;

    name: string;

    city?: string | null;

    country?: string | null;

  };

}









export default function ArtistProfilePage() {


  const params =
    useParams();


  const router =
    useRouter();




  const artistSlug =
    params.slug as string;






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




  const [
    following,
    setFollowing,
  ] = useState(false);




  const [
    followLoading,
    setFollowLoading,
  ] = useState(false);









  useEffect(() => {


    const token =
      localStorage.getItem(
        'token'
      );



    if (!token) {


      router.push(
        '/login'
      );


      return;

    }



    if (artistSlug) {

      loadArtist();

      loadArtistEvents();

      loadFollowStatus();

    }



  }, [artistSlug]);









  async function loadArtist() {


    try {


      setLoading(true);



      const data =
        await artistAPI.getArtist(
          artistSlug
        );



      setArtist(
        data
      );



    } catch(error) {


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









  async function loadArtistEvents() {


    try {


      const data =
        await eventAPI.getArtistEvents(
          artistSlug
        );



      setEvents(
        data
      );



    } catch(error) {


      console.error(
        'Failed to load artist events:',
        error
      );


    }


  }









  async function loadFollowStatus() {


    try {


      const data =
        await artistAPI.getFollowStatus(
          artistSlug
        );



      setFollowing(
        data.following
      );



    } catch(error) {


      console.error(
        'Failed to load follow status:',
        error
      );


    }


  }









  async function handleFollow() {


    try {


      setFollowLoading(
        true
      );



      if (following) {


        await artistAPI.unfollowArtist(
          artistSlug
        );



        setFollowing(
          false
        );



      } else {


        await artistAPI.followArtist(
          artistSlug
        );



        setFollowing(
          true
        );


      }



    } catch(error) {


      console.error(
        'Failed to update follow:',
        error
      );



    } finally {


      setFollowLoading(
        false
      );


    }


  }









  if (loading) {


    return (

      <div className="
        min-h-screen
        flex
        items-center
        justify-center
      ">


        <LoadingState message="Loading artist..." />


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


        <p className="text-red-400">

          {
            error ||
            'Artist not found.'
          }

        </p>



        <Link

          href="/artists"

          className="
            text-accent
            hover:text-accent/80
          "

        >

          Back to artists


        </Link>


      </div>

    );


  }









  return (

    <div className="min-h-screen">









      <main className="
        max-w-5xl
        mx-auto
        px-4
        py-10
      ">





        <Card className="overflow-hidden p-0">





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






          <div className="p-8">





            <div className="
              flex
              items-center
              justify-between
              mb-6
            ">


              <h1 className="
                text-[36px]
                font-bold
              ">

                {artist.name}

              </h1>





              <Button
                onClick={handleFollow}
                disabled={followLoading}
                variant={following ? 'outline' : 'primary'}
              >

                {
                  followLoading
                  ?
                  'Loading...'
                  :
                  following
                  ?
                  'Following ✓'
                  :
                  'Follow'
                }


              </Button>


            </div>









            {
              artist.genres?.length > 0 && (

                <div className="mb-8">


                  <h2 className="
                    text-[14px]
                    text-gray-400
                    mb-2
                  ">

                    Genres

                  </h2>




                  <div className="
                    flex
                    flex-wrap
                    gap-2
                  ">


                    {
                      artist.genres.map(
                        genre => (

                          <Badge key={genre} variant="outline">
                            {genre}
                          </Badge>

                        )
                      )
                    }


                  </div>


                </div>

              )
            }









            {
              artist.events && (

                <div className="
                  grid
                  md:grid-cols-2
                  gap-4
                  mb-8
                ">


                  <div className="
                    bg-card-hover
                    rounded-lg
                    p-4
                  ">


                    <p className="text-gray-400">

                      Upcoming Events

                    </p>


                    <p className="text-[24px] font-bold">

                      {artist.events.upcoming}

                    </p>


                  </div>




                  <div className="
                    bg-card-hover
                    rounded-lg
                    p-4
                  ">


                    <p className="text-gray-400">

                      Total Events

                    </p>


                    <p className="text-[24px] font-bold">

                      {artist.events.total}

                    </p>


                  </div>


                </div>

              )
            }







            <section>


              <h2 className="
                text-[24px]
                font-bold
                mb-4
              ">

                Events

              </h2>





              {
                events.length === 0 ? (


                  <p className="text-gray-400">

                    No events found.

                  </p>


                ) : (


                  <div className="
                    space-y-4
                  ">


                    {
                      events.map(
                        event => (


                          <Link

                            key={event.id}

                            href={`/events/${event.id}`}

                            className="
                              block
                              bg-card-hover
                              border
                              border-border
                              rounded-lg
                              p-4
                              hover:border-accent
                              transition
                            "

                          >


                            <h3 className="
                              font-semibold
                            ">

                              {event.title}

                            </h3>



                            <p className="
                              text-gray-400
                              mt-2
                            ">

                              {
                                new Date(
                                  event.starts_at
                                ).toLocaleDateString(
                                  'en-US',
                                  {
                                    year:'numeric',
                                    month:'long',
                                    day:'numeric'
                                  }
                                )
                              }

                            </p>



                          </Link>


                        )
                      )
                    }


                  </div>


                )
              }


            </section>





          </div>


        </Card>


      </main>


    </div>

  );


}