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
import { useTranslations } from 'next-intl';

import {
  eventAPI,
  artistAPI,
} from '../../../../lib/api';

import Card from '../../../../../components/ui/Card';
import Input from '../../../../../components/ui/Input';
import Badge from '../../../../../components/ui/Badge';
import LoadingState from '../../../../../components/LoadingState';
import EventCard from '../../../../../components/EventCard';

import ArtistTabs from '../../../../../components/artist/ArtistTabs';



interface Artist {

  name: string;

  image?: string;

  /*
    Present only when the backend ran a first-open synchronization while
    answering this read; the events request beside it may predate what that
    fetch stored, which is why the listing is re-read when it says so.
  */
  sync?: {

    attempted?: boolean;

  } | null;

}



interface ArtistEvent {

  id: string;

  title: string;

  // Nullable: imported events arrive without a date often enough that the
  // type has to admit it rather than promise a string.
  starts_at: string | null;

  ticket_url?: string | null;

  venue?: {

    name?: string | null;

    slug?: string | null;

    city?: string | null;

    country?: string | null;

  } | null;

  going_count?: number;

  maybe_count?: number;

  went_count?: number;

}


/**
 * When an event starts, or `Infinity` when it has no usable date.
 *
 * Undated shows sort last instead of producing `NaN`, which no comparator can
 * order and which used to scatter them arbitrarily through the list.
 */
function eventStart(event: ArtistEvent): number {

  const parsed = event.starts_at
    ? new Date(event.starts_at).getTime()
    : Number.NaN;

  return Number.isFinite(parsed)
    ? parsed
    : Number.POSITIVE_INFINITY;

}


/**
 * The year an event starts in, or `null` when it has no usable date.
 *
 * Only usable dates reach the year filter, so an undated show cannot claim
 * "NaN" as its year - and it stays visible under "All years", where the
 * honest answer is that nobody has said when it is.
 */
function eventYear(event: ArtistEvent): number | null {

  const parsed = event.starts_at
    ? new Date(event.starts_at).getTime()
    : Number.NaN;

  if (!Number.isFinite(parsed)) {
    return null;
  }

  return new Date(parsed).getFullYear();

}







export default function ArtistEventsPage(){


  const params =
    useParams();


  const artistSlug =
    params.slug as string;

  const locale =
    (params.locale as string) || 'en';

  const t =
    useTranslations('artistEvents');

  const tArtist =
    useTranslations('artist');





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


      /*
        A first open of a pending artist initializes them inside this same
        read, and the listing requested beside it answered before that fetch
        stored anything. When the response says a synchronization just ran,
        the listing is read again so it shows what the sync stored.
      */
      if (data?.sync?.attempted) {

        await loadEvents();

      }


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
            eventStart(a)
            -
            eventStart(b)
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
        events
        .map(eventYear)
        .filter(
          (year): year is number =>
            year !== null
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



        const year =
          eventYear(event);


        const matchesYear =
          selectedYear === 'all'
          ||
          (
            year !== null
            &&
            year.toString()
            === selectedYear
          );



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

        <LoadingState message={t('loading')} />

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

          href={`/${locale}/artists/${artistSlug}`}

          className="
            text-accent-text
            underline-offset-2
            hover:underline
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



        <ArtistTabs

          locale={locale}

          slug={artistSlug}

          active="events"

        />









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
                py-2.5
                min-h-[44px]
                text-foreground
              "

            >


              <option value="all">{t('allYears')}</option>



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


              <p className="text-muted">{t('noEvents')}</p>


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