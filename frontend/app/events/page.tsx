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

  _id: string;

  title: string;

  artist_name: string;

  venue_name: string;

  date: string;

  location: string;

  image_url?: string;

  status: string;

  going_count: number;

  maybe_count: number;

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
    searchQuery,
    setSearchQuery,
  ] = useState('');




  const [
    loading,
    setLoading,
  ] = useState(false);




  const [
    searching,
    setSearching,
  ] = useState(false);




  const [
    eventMode,
    setEventMode,
  ] = useState<EventMode>('all');




  const [
    specificDate,
    setSpecificDate,
  ] = useState('');








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









  async function handleSearch(
    e: React.FormEvent
  ) {


    e.preventDefault();



    if (!searchQuery.trim()) {

      loadEvents();

      return;

    }



    try {


      setSearching(true);



      if (specificDate) {


        const data =
          await eventAPI.searchExternal(
            searchQuery,
            undefined,
            specificDate,
            undefined,
            undefined
          );


        setEvents(
          data.events || []
        );



      } else {



        const eventType =
          eventMode === 'all'
            ? 'future'
            : eventMode;



        const data =
          await eventAPI.searchExternal(
            searchQuery,
            eventType,
            undefined,
            undefined,
            undefined
          );



        setEvents(
          data.events || []
        );

      }



    } catch(error) {


      console.error(
        'Failed to search events:',
        error
      );


    } finally {


      setSearching(false);


    }


  }









  function getDateConstraints() {


    const today =
      new Date();



    today.setHours(
      0,
      0,
      0,
      0
    );



    const yesterday =
      new Date(today);



    yesterday.setDate(
      yesterday.getDate() - 1
    );



    if(eventMode === 'past') {


      return {

        max:
          yesterday
            .toISOString()
            .split('T')[0]

      };


    }



    if(eventMode === 'future') {


      return {

        min:
          today
            .toISOString()
            .split('T')[0]

      };


    }



    return {};

  }









  return (

    <div className="min-h-screen">


      <header className="border-b border-gray-800 px-4 py-4">

        <div className="max-w-6xl mx-auto flex items-center justify-between">


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
              className="text-gray-400 hover:text-white transition-colors"
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
                transition-colors
              "

            >

              Profile


            </Link>



          </nav>


        </div>


      </header>






      <main className="max-w-6xl mx-auto px-4 py-8">


        <h1 className="text-3xl font-bold mb-6">

          Discover Events

        </h1>





        <div className="mb-6">


          <label className="block text-sm font-medium text-gray-300 mb-2">

            Event Mode

          </label>



          <select

            value={eventMode}

            onChange={
              (e) => {

                setEventMode(
                  e.target.value as EventMode
                );

                setSpecificDate('');

              }
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


            <option value="past">
              Past Events
            </option>


            <option value="future">
              Future Events
            </option>


          </select>


        </div>







        <form
          onSubmit={handleSearch}
          className="mb-8"
        >


          <div className="flex flex-col gap-4">


            <input

              type="text"

              value={searchQuery}

              onChange={
                (e) =>
                  setSearchQuery(
                    e.target.value
                  )
              }


              placeholder="Search for artists..."


              className="
                px-4
                py-3
                bg-gray-800
                border
                border-gray-700
                rounded-lg
                text-white
              "

            />




            {
              eventMode !== 'all' && (

                <input

                  type="date"

                  value={specificDate}

                  onChange={
                    (e) =>
                      setSpecificDate(
                        e.target.value
                      )
                  }


                  {...getDateConstraints()}

                  className="
                    px-4
                    py-2
                    bg-gray-800
                    border
                    border-gray-700
                    rounded-lg
                    text-white
                  "

                />

              )
            }






            <button

              disabled={searching}

              className="
                px-6
                py-3
                bg-purple-600
                hover:bg-purple-700
                text-white
                rounded-lg
              "

            >

              {
                searching
                  ? 'Searching...'
                  : 'Search'
              }


            </button>


          </div>


        </form>







        {
          loading ? (


            <div className="text-center py-12">

              Loading events...

            </div>



          ) : events.length === 0 ? (


            <div className="text-center py-12 text-gray-400">

              No events found.

            </div>



          ) : (



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
                events.map(
                  (event) => (


                    <Link

                      key={event._id}

                      href={`/events/${event._id}`}

                      className="
                        bg-gray-900
                        border
                        border-gray-800
                        rounded-lg
                        overflow-hidden
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


                        <h3 className="font-semibold">

                          {event.title}

                        </h3>


                        <p className="text-gray-400">

                          {event.artist_name}

                        </p>


                        <p className="text-gray-400">

                          {
                            format(
                              new Date(event.date),
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