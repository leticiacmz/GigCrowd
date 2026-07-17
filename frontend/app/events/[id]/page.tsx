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
  userAPI,
} from '../../lib/api';

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
    attendStatus,
    setAttendStatus,
  ] = useState<
    'going' | 'maybe' | 'went' | null
  >(null);





  const [
    notes,
    setNotes,
  ] = useState('');









  useEffect(()=>{


    const token =
      localStorage.getItem('token');



    if(!token){

      router.push('/login');

      return;

    }



    loadEvent();

    loadCurrentUser();



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











  async function handleAttend(

    status:
      'going'
      | 'maybe'
      | 'went'

  ){


    try{


      setSubmitting(true);



      await eventAPI.attendEvent(

        eventId,

        status,

        notes || undefined

      );



      setAttendStatus(status);



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

        <p className="text-gray-400">
          Loading event...
        </p>

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

            href="/events"

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



          <nav className="flex gap-4">


            <Link
              href="/artists"
              className="text-gray-400 hover:text-white"
            >
              Artists
            </Link>


            <Link
              href="/events"
              className="text-gray-400 hover:text-white"
            >
              Events
            </Link>



            <Link

              href={
                currentUser
                  ? `/profile/${currentUser.username}`
                  : '/login'
              }

              className="text-gray-400 hover:text-white"

            >

              Profile

            </Link>


          </nav>


        </div>


      </header>









      <main className="
        max-w-5xl
        mx-auto
        px-4
        py-8
      ">



        <Link

          href="/events"

          className="
            text-purple-400
            hover:text-purple-300
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
              text-4xl
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
                        text-purple-400
                        hover:text-purple-300
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
                      px-4
                      py-2
                      bg-purple-600
                      rounded-lg
                    "

                  >

                    Tickets

                  </a>

                )
              }




            </div>


          </div>









          <div>


            <div className="
              bg-gray-900
              border
              border-gray-800
              rounded-lg
              p-6
            ">


              <h2 className="
                text-xl
                font-bold
                mb-4
              ">

                Your attendance

              </h2>





              <div className="space-y-3">


                <button

                  disabled={submitting}

                  onClick={() =>
                    handleAttend('going')
                  }

                  className="
                    w-full
                    py-3
                    rounded-lg
                    bg-gray-800
                  "

                >

                  ✓ I'm going

                </button>





                <button

                  disabled={submitting}

                  onClick={() =>
                    handleAttend('maybe')
                  }

                  className="
                    w-full
                    py-3
                    rounded-lg
                    bg-gray-800
                  "

                >

                  ? Maybe

                </button>






                <button

                  disabled={submitting}

                  onClick={() =>
                    handleAttend('went')
                  }

                  className="
                    w-full
                    py-3
                    rounded-lg
                    bg-gray-800
                  "

                >

                  ✓ I went

                </button>


              </div>








              <div className="
                border-t
                border-gray-700
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



            </div>


          </div>





        </div>



      </main>


    </div>


  );


}