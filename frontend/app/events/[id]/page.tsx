'use client';

import {
  useEffect,
  useState,
} from 'react';

import {
  useRouter,
  useParams,
} from 'next/navigation';

import Link from 'next/link';

import {
  eventAPI,
  showLogAPI,
  userAPI,
} from '../../lib/api';

import Button from '../../../components/ui/Button';
import Card from '../../../components/ui/Card';
import LoadingState from '../../../components/LoadingState';

import {
  format,
} from 'date-fns';


interface Event {

  _id: string;

  title: string;

  artist_slug?: string;

  venue_slug?: string;

  starts_at: string;

  ticket_url?: string | null;

  sold_out?: boolean;

  free?: boolean;

  going_count?: number;

  maybe_count?: number;

  went_count?: number;

  description?: string;

  image_url?: string;

}




export default function EventDetailPage(){


  const router = useRouter();

  const params = useParams();



  const eventId =
    params.id as string;




  const [
    event,
    setEvent,
  ] = useState<Event | null>(null);



  const [
    currentUser,
    setCurrentUser,
  ] = useState<any>(null);



  const [
    loading,
    setLoading,
  ] = useState(true);



  const [
    submitting,
    setSubmitting,
  ] = useState(false);



  const [
  review,
  setReview,
  ] = useState('');


  const [
  rating,
  setRating,
  ] = useState<number | null>(null);



  useEffect(()=>{


    loadEvent();


    const token =
      localStorage.getItem('token');


    if(token){

      loadCurrentUser();

    }


  },[eventId]);







  async function loadCurrentUser(){


    try{


      const user =
        await userAPI.getMe();


      setCurrentUser(user);


    }catch(error){


      console.error(
        'Failed loading user',
        error
      );


    }


  }







  async function loadEvent(){


    try{


      setLoading(true);



      const data =
        await eventAPI.getEvent(
          eventId
        );


      setEvent(data);



    }catch(error){


      console.error(
        'Failed loading event',
        error
      );


    }finally{


      setLoading(false);


    }


  }







  function requireLogin(
    callback: () => void
  ){


    const token =
      localStorage.getItem('token');


    if(!token){

      router.push('/login');

      return;

    }


    callback();

  }







  async function handleAttend(

  status:
    'going'
    | 'maybe'
    | 'went'

){


    try{


      setSubmitting(true);



     await showLogAPI.create({

        event_id: eventId,

        status,

        rating: rating ?? undefined,

        review: review || undefined,

      });



      await loadEvent();



    }catch(error){


      console.error(
        'Failed updating attendance',
        error
      );


    }finally{


      setSubmitting(false);


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

        <LoadingState message="Loading event..." />

      </div>

    );


  }







  if(!event){


    return (

      <div className="
        min-h-screen
        flex
        items-center
        justify-center
      ">

        <p className="text-gray-400">
          Event not found.
        </p>

      </div>

    );


  }







  return (

    <div className="min-h-screen">


      <main className="
        max-w-5xl
        mx-auto
        px-4
        py-8
      ">


        <Link
          href="/events"
          className="
            text-accent
            hover:text-accent/80
          "
        >

          ← Back to events

        </Link>





        <div className="
          mt-6
          grid
          grid-cols-1
          lg:grid-cols-3
          gap-8
        ">





          <div className="
            lg:col-span-2
          ">



            {
              event.image_url && (

                <img

                  src={event.image_url}

                  alt={event.title}

                  className="
                    w-full
                    h-72
                    object-cover
                    rounded-lg
                    mb-6
                  "

                />

              )
            }






            <h1 className="
              text-[36px]
              font-bold
              mb-6
            ">

              {event.title}

            </h1>






            <div className="space-y-4">


              <div>

                <h2 className="font-semibold">
                  Date
                </h2>


                <p className="text-gray-400">

                  {
                    format(
                      new Date(event.starts_at),
                      'MMMM d, yyyy • h:mm a'
                    )
                  }

                </p>


              </div>






              {
                event.artist_slug && (

                  <div>

                    <h2 className="font-semibold">
                      Artist
                    </h2>


                    <Link

                      href={`/artists/${event.artist_slug}`}

                      className="
                        text-accent
                        hover:text-accent/80
                      "

                    >

                      {event.artist_slug}

                    </Link>


                  </div>

                )
              }





              {
                event.venue_slug && (

                  <div>

                    <h2 className="font-semibold">
                      Venue
                    </h2>


                    <p className="text-gray-400">

                      {event.venue_slug}

                    </p>


                  </div>

                )
              }





              {
                event.ticket_url && (

                  <a

                    href={event.ticket_url}

                    target="_blank"

                    className="
                      inline-block
                      mt-4
                    "

                  >

                    <Button variant="primary">
                      Tickets
                    </Button>

                  </a>

                )
              }





            </div>


          </div>








          <div>


            <Card className="p-6">


              <h2 className="
                text-[18px]
                font-bold
                mb-4
              ">

                Your attendance

              </h2>





              <div className="space-y-3">



                <Button

                  disabled={submitting}

                  onClick={() =>
                    requireLogin(() =>
                      handleAttend('going')
                    )
                  }

                  variant="outline"

                  className="w-full"

                >

                  ✓ I'm going

                </Button>





                <Button

                  disabled={submitting}

                  onClick={() =>
                    requireLogin(() =>
                      handleAttend('maybe')
                    )
                  }

                  variant="outline"

                  className="w-full"

                >

                  ? Maybe

                </Button>





                <Button

                  disabled={submitting}

                  onClick={() =>
                    requireLogin(() =>
                      handleAttend('went')
                    )
                  }

                  variant="outline"

                  className="w-full"

                >

                  ✓ I went

                </Button>



              </div>





              <div className="
                border-t
                border-border
                mt-6
                pt-4
              ">


                <div className="
                  grid
                  grid-cols-3
                  text-center
                ">


                  <div>

                    <strong>
                      {event.going_count ?? 0}
                    </strong>

                    <p className="text-gray-400 text-sm">
                      Going
                    </p>

                  </div>



                  <div>

                    <strong>
                      {event.maybe_count ?? 0}
                    </strong>

                    <p className="text-gray-400 text-sm">
                      Maybe
                    </p>

                  </div>




                  <div>

                    <strong>
                      {event.went_count ?? 0}
                    </strong>

                    <p className="text-gray-400 text-sm">
                      Went
                    </p>

                  </div>


                </div>


              </div>



            </Card>


          </div>





        </div>



      </main>


    </div>

  );

}