'use client';

import {
  useEffect,
  useMemo,
  useState,
} from 'react';

import {
  useParams,
} from 'next/navigation';

import Link from 'next/link';

import {
  eventAPI,
  artistAPI,
} from '../../../lib/api';

import Card from '../../../../components/ui/Card';
import Input from '../../../../components/ui/Input';
import Badge from '../../../../components/ui/Badge';
import LoadingState from '../../../../components/LoadingState';
import EventCard from '../../../../components/EventCard';



interface Artist {

  name: string;

  image?: string;

}



interface ArtistEvent {

  id: string;

  title: string;

  starts_at: string;

  ticket_url?: string | null;

  venue?: {

    name: string;

    city?: string | null;

    country?: string | null;

  };

  going_count?: number;

  maybe_count?: number;

  went_count?: number;

}







export default function ArtistEventsPage(){


  const params =
    useParams();


  const artistSlug =
    params.slug as string;





  const [
    artist,
    setArtist,
  ] = useState<Artist | null>(null);





  const [
    events,
    setEvents,
  ] = useState<ArtistEvent[]>([]);





  const [
    loading,
    setLoading,
  ] = useState(true);





  const [
    search,
    setSearch,
  ] = useState('');





  const [
    selectedYear,
    setSelectedYear,
  ] = useState('all');









  useEffect(()=>{


    if(!artistSlug){
      return;
    }


    loadArtist();

    loadEvents();


  },[artistSlug]);








  async function loadArtist(){


    try{


      const data =
        await artistAPI.getArtist(
          artistSlug
        );


      setArtist(data);


    }catch(error){


      console.error(
        'Failed loading artist',
        error
      );


    }


  }








  async function loadEvents(){


    try{


      setLoading(true);


      const data =
        await eventAPI.getAllArtistEvents(
          artistSlug
        );


      const sorted =
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
        sorted
      );


    }catch(error){


      console.error(
        'Failed loading events',
        error
      );


    }finally{


      setLoading(false);


    }


  }









  const years =
    useMemo(()=>{


      const values =
        events.map(
          event =>
            new Date(
              event.starts_at
            ).getFullYear()
        );


     return Array.from(
        new Set(values)
        )
        .sort(
        (
            a,
            b
        ) =>
            b - a
        );


    },[events]);









  const filteredEvents =

    events.filter(
      event => {


        const text =
          `

          ${event.title}

          ${event.venue?.name}

          ${event.venue?.city}

          ${event.venue?.country}

          `
          .toLowerCase();



        const matchesSearch =
          text.includes(
            search.toLowerCase()
          );



        const matchesYear =
          selectedYear === 'all'
          ||
          new Date(
            event.starts_at
          )
          .getFullYear()
          .toString()
          === selectedYear;



        return (
          matchesSearch &&
          matchesYear
        );


      }
    );









  if(loading){


    return (

      <div className="
        min-h-screen
        flex
        items-center
        justify-center
      ">

        <LoadingState message="Loading events..." />

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



        <Link

          href={`/artists/${artistSlug}`}

          className="
            text-accent
            hover:text-accent/80
          "

        >

          ← Back to artist

        </Link>







        <div className="mt-6">


          <h1 className="
            text-[36px]
            font-bold
          ">

            {artist?.name}

          </h1>



        </div>









        <Card className="
          mt-8
          p-6
        ">



          <div className="
            grid
            md:grid-cols-2
            gap-4
            mb-8
          ">


            <Input

              value={search}

              onChange={
                e =>
                  setSearch(
                    e.target.value
                  )
              }

              placeholder="
                Search events, cities...
              "

            />





            <select

              value={selectedYear}

              onChange={
                e =>
                  setSelectedYear(
                    e.target.value
                  )
              }

              className="
                rounded-lg
                bg-card-bg
                border
                border-border
                px-3
                text-gray-300
              "

            >


              <option value="all">

                All years

              </option>



              {
                years.map(
                  year => (

                    <option

                      key={year}

                      value={year}

                    >

                      {year}

                    </option>

                  )
                )
              }


            </select>


          </div>







          <div className="
            flex
            flex-wrap
            gap-2
            mb-6
          ">


            <Badge variant="accent">

              {filteredEvents.length} events

            </Badge>


          </div>









          {
            filteredEvents.length === 0 ? (


              <p className="text-gray-400">

                No events found.

              </p>


            ) : (


              <div className="
                grid
                grid-cols-1
                md:grid-cols-2
                gap-5
              ">


                {
                  filteredEvents.map(
                    event => (

                      <EventCard

                        key={event.id}

                        event={event}

                      />

                    )
                  )
                }


              </div>


            )

          }





        </Card>



      </main>


    </div>


  );


}