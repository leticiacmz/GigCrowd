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

  artist_name: string;

  venue_name: string;

  date: string;

  location: string;

  city: string;

  country: string;

  description?: string;

  image_url?: string;

  ticket_url?: string;

  status: string;

  going_count: number;

  maybe_count: number;

  went_count: number;

  setlist?: string[];

  setlist_count?: number;

}







export default function EventDetailPage() {


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
    attendStatus,
    setAttendStatus,
  ] = useState<
    'going' | 'maybe' | 'went' | null
  >(null);




  const [
    notes,
    setNotes,
  ] = useState('');




  const [
    submitting,
    setSubmitting,
  ] = useState(false);








  useEffect(() => {


    const token =
      localStorage.getItem('token');



    if(!token){

      router.push('/login');

      return;

    }



    loadEvent();

    loadCurrentUser();



  }, [eventId, router]);









  async function loadCurrentUser(){


    try{


      const user =
        await userAPI.getMe();



      setCurrentUser(
        user
      );


    }catch(error){


      console.error(
        'Failed to load user:',
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



      setEvent(
        data
      );


    }catch(error){


      console.error(
        'Failed to load event:',
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



      setAttendStatus(
        status
      );



      loadEvent();



    }catch(error){


      console.error(
        'Failed to mark attendance:',
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

        <div className="text-gray-400">

          Loading event...

        </div>

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

        <div className="text-gray-400">

          Event not found

        </div>


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
          items-center
          justify-between
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






          <nav className="flex items-center gap-4">


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









      <main className="
        max-w-6xl
        mx-auto
        px-4
        py-8
      ">


        <Link

          href="/events"

          className="
            inline-block
            mb-6
            text-purple-400
          "

        >

          ← Back to Events


        </Link>









        <div className="
          grid
          grid-cols-1
          lg:grid-cols-3
          gap-8
        ">





          <div className="lg:col-span-2">


            {
              event.image_url && (

                <img

                  src={event.image_url}

                  alt={event.title}

                  className="
                    w-full
                    h-64
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
              mb-4
            ">

              {event.title}


            </h1>





            <div className="space-y-4">


              <div>

                <h2 className="font-semibold">

                  Artist

                </h2>


                <p className="text-gray-400">

                  {event.artist_name}

                </p>


              </div>





              <div>

                <h2 className="font-semibold">

                  Venue

                </h2>


                <p className="text-gray-400">

                  {event.venue_name}

                </p>


              </div>





              <div>

                <h2 className="font-semibold">

                  Date

                </h2>


                <p className="text-gray-400">

                  {
                    format(
                      new Date(event.date),
                      'MMMM d, yyyy • h:mm a'
                    )
                  }

                </p>


              </div>





              <div>

                <h2 className="font-semibold">

                  Location

                </h2>


                <p className="text-gray-400">

                  {event.location}

                </p>


                <p className="text-gray-500">

                  {event.city}, {event.country}

                </p>


              </div>






              {
                event.description && (

                  <div>

                    <h2 className="font-semibold">

                      Description

                    </h2>


                    <p className="text-gray-400">

                      {event.description}

                    </p>


                  </div>

                )
              }




            </div>



          </div>








          <div className="lg:col-span-1">


            <div className="
              bg-gray-900
              border
              border-gray-800
              rounded-lg
              p-6
            ">


              <h2 className="text-xl font-bold mb-4">

                Mark Your Attendance

              </h2>





              <div className="space-y-3">


                <button

                  onClick={() =>
                    handleAttend('going')
                  }

                  className="
                    w-full
                    py-3
                    rounded-lg
                    bg-gray-800
                    text-white
                  "

                >

                  ✓ Going


                </button>





                <button

                  onClick={() =>
                    handleAttend('maybe')
                  }

                  className="
                    w-full
                    py-3
                    rounded-lg
                    bg-gray-800
                    text-white
                  "

                >

                  ? Maybe


                </button>





                <button

                  onClick={() =>
                    handleAttend('went')
                  }

                  className="
                    w-full
                    py-3
                    rounded-lg
                    bg-gray-800
                    text-white
                  "

                >

                  ✓ Went


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

                    <p className="text-xl font-bold">

                      {event.going_count}

                    </p>


                    <p className="text-gray-400 text-sm">

                      Going

                    </p>


                  </div>



                  <div>

                    <p className="text-xl font-bold">

                      {event.maybe_count}

                    </p>


                    <p className="text-gray-400 text-sm">

                      Maybe

                    </p>


                  </div>




                  <div>

                    <p className="text-xl font-bold">

                      {event.went_count}

                    </p>


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