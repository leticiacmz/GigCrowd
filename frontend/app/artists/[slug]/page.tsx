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
import EventCard from '../../../components/EventCard';



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


  going_count?: number;

  maybe_count?: number;

  went_count?: number;

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


    if (artistSlug) {


      loadArtist();

      loadArtistEvents();


    }


    const token =
      localStorage.getItem('token');


    if(token){

      loadFollowStatus();

    }



  },[artistSlug]);








  async function loadArtist(){


    try{


      setLoading(true);



      const data =
        await artistAPI.getArtist(
          artistSlug
        );



      setArtist(
        data
      );



    }catch(error){


      console.error(
        'Failed to load artist:',
        error
      );



      setError(
        'Could not load artist profile.'
      );



    }finally{


      setLoading(false);


    }


  }








  async function loadArtistEvents(){


    try{


      const data =
        await eventAPI.getArtistEvents(
          artistSlug
        );



      const sortedEvents =
        [...data].sort(
          (
            a,
            b
          ) =>
            new Date(a.starts_at).getTime()
            -
            new Date(b.starts_at).getTime()
        );



      setEvents(
        sortedEvents
      );



    }catch(error){


      console.error(
        'Failed to load artist events:',
        error
      );


    }


  }









  async function loadFollowStatus(){


    try{


      const data =
        await artistAPI.getFollowStatus(
          artistSlug
        );



      setFollowing(
        data.following
      );



    }catch(error){


      console.error(
        'Failed to load follow status:',
        error
      );


    }


  }









  async function handleFollow(){


    try{


      setFollowLoading(
        true
      );



      if(following){


        await artistAPI.unfollowArtist(
          artistSlug
        );



        setFollowing(
          false
        );



      }else{


        await artistAPI.followArtist(
          artistSlug
        );



        setFollowing(
          true
        );


      }



    }catch(error){


      console.error(
        'Failed to update follow:',
        error
      );



    }finally{


      setFollowLoading(
        false
      );


    }


  }









  if(loading){


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









  if(error || !artist){


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








  const upcomingEvents =

    events

      .filter(
        event =>
          new Date(event.starts_at) >= new Date()
      )

      .slice(
        0,
        6
      );







  return (

    <div className="min-h-screen">


      <main className="
        max-w-5xl
        mx-auto
        px-4
        py-10
      ">





        <Card className="
          overflow-hidden
          p-0
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

                onClick={() => {

                  const token =
                    localStorage.getItem(
                      'token'
                    );


                  if(!token){

                    router.push('/login');

                    return;

                  }


                  handleFollow();


                }}

                disabled={followLoading}

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

                          <Badge
                            key={genre}
                            variant="outline"
                          >

                            {genre}

                          </Badge>

                        )
                      )
                    }


                  </div>


                </div>

              )
            }









            <section className="mt-8">


              <div className="
                flex
                items-center
                justify-between
                mb-5
              ">


                <h2 className="
                  text-[24px]
                  font-bold
                ">

                  Upcoming Events

                </h2>




                {
                  artist.events &&
                  artist.events.total > 6 && (

                    <Link

                      href={`/artists/${artistSlug}/events`}

                      className="
                        text-sm
                        text-accent
                        hover:text-accent/80
                      "

                    >

                      See all events →

                    </Link>

                  )
                }


              </div>








              {
                upcomingEvents.length === 0 ? (


                  <p className="text-gray-400">

                    No upcoming events.

                  </p>


                ) : (



                  <div

                    className={`

                      ${
                        upcomingEvents.length <= 3

                        ?

                        'grid grid-cols-1 md:grid-cols-3 gap-4'

                        :

                        upcomingEvents.length === 4

                        ?

                        'grid grid-cols-1 md:grid-cols-4 gap-4'

                        :

                        'flex gap-4 overflow-x-auto pb-3 snap-x'

                      }

                    `}

                  >


                    {
                      upcomingEvents.map(
                        event => (

                          <div

                            key={event.id}

                            className={`
                              ${
                                upcomingEvents.length > 4
                                ?
                                'min-w-[280px] snap-start'
                                :
                                ''
                              }
                            `}

                          >

                            <EventCard
                              event={event}
                            />


                          </div>

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