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
  eventAPI,
  userAPI,
} from '../lib/api';

import {
  format,
} from 'date-fns';



interface Event {

  id: string;

  title: string;

  artist_name?: string;

  venue_name?: string;

  starts_at: string;

  location?: string;

  image_url?: string;

  status?: string;

  going_count?: number;

  maybe_count?: number;

}



type EventMode =
  | 'all'
  | 'past'
  | 'future';





export default function EventsPage() {


  const router = useRouter();



  const [
    events,
    setEvents,
  ] = useState<Event[]>([]);




  const [
    currentUser,
    setCurrentUser,
  ] = useState<any>(null);




  const [
    loading,
    setLoading,
  ] = useState(false);




  const [
    eventMode,
    setEventMode,
  ] = useState<EventMode>('all');






  useEffect(() => {


    const token =
      localStorage.getItem('token');



    if (!token) {

      router.push('/login');

      return;

    }



    loadEvents();

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









  async function loadEvents() {


    try {


      setLoading(true);



      const data =
        await eventAPI.getEvents();



      setEvents(
        data
      );



    } catch(error) {


      console.error(
        'Failed to load events:',
        error
      );


    } finally {


      setLoading(false);


    }


  }








  function filteredEvents() {


    if(eventMode === 'all') {

      return events;

    }



    const now =
      new Date();



    return events.filter(
      event => {


        const eventDate =
          new Date(
            event.starts_at
          );



        if(eventMode === 'past') {

          return eventDate < now;

        }



        return eventDate >= now;


      }
    );


  }







  return (

    <div className="min-h-screen">


      <header className="border-b border-gray-800 px-4 py-4">


        <div className="
          max-w-6xl
          mx-auto
          flex
          items-center
          justify-between
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


        <h1 className="
          text-3xl
          font-bold
          mb-6
        ">

          Discover Events


        </h1>







        <div className="mb-8">


          <label className="
            block
            text-sm
            text-gray-300
            mb-2
          ">

            Event Mode


          </label>





          <select

            value={eventMode}

            onChange={
              e =>
                setEventMode(
                  e.target.value as EventMode
                )
            }


            className="
              w-full
              px-4
              py-3
              bg-gray-800
              border
              border-gray-700
              rounded-lg
              text-white
            "

          >


            <option value="all">
              All Events
            </option>


            <option value="future">
              Upcoming Events
            </option>


            <option value="past">
              Past Events
            </option>


          </select>


        </div>









        {
          loading ? (


            <div className="
              text-center
              py-12
            ">

              Loading events...


            </div>



          ) : filteredEvents().length === 0 ? (


            <div className="
              text-center
              py-12
              text-gray-400
            ">

              No events found.


            </div>



          ) : (



            <div className="
              grid
              grid-cols-1
              md:grid-cols-2
              lg:grid-cols-3
              gap-6
            ">


              {
                filteredEvents().map(
                  event => (


                    <Link

                      key={event.id}

                      href={`/events/${event.id}`}


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
                        event.image_url && (

                          <img

                            src={event.image_url}

                            alt={event.title}

                            className="
                              w-full
                              h-48
                              object-cover
                            "

                          />

                        )
                      }







                      <div className="p-4">


                        <h3 className="
                          font-semibold
                          text-white
                        ">

                          {event.title}


                        </h3>





                        {
                          event.artist_name && (

                            <p className="
                              text-gray-400
                            ">

                              {event.artist_name}


                            </p>

                          )
                        }







                        <p className="
                          text-gray-400
                          mt-2
                        ">


                          {
                            format(
                              new Date(
                                event.starts_at
                              ),
                              'MMM d, yyyy'
                            )
                          }


                        </p>



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