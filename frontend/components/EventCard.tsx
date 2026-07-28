import Link from 'next/link';

import {
  format,
} from 'date-fns';

import Card from './ui/Card';
import Badge from './ui/Badge';


interface EventCardProps {

  event: {

    id: string;

    title: string;

    starts_at: string;

    venue?: {

      name: string;

      city?: string | null;

      country?: string | null;

    } | null;


    going_count?: number;

    maybe_count?: number;

    went_count?: number;

  };

}





export default function EventCard({
  event,
}: EventCardProps) {


  const formattedDate =
    format(
      new Date(event.starts_at),
      'MMM d, yyyy'
    );



  const formattedTime =
    format(
      new Date(event.starts_at),
      'h:mm a'
    );




  return (

    <Link
      href={`/events/${event.id}`}
      className="block"
    >


      <Card
        hoverable
        className="
          h-full
          p-5
          transition
        "
      >


        <div className="
          flex
          flex-col
          h-full
        ">



          <div className="
            flex
            items-start
            justify-between
            gap-3
            mb-4
          ">


            <h3 className="
              font-semibold
              text-lg
              line-clamp-2
            ">

              {event.title}

            </h3>



            <Badge
              variant="accent"
              size="sm"
            >

              {formattedDate}

            </Badge>


          </div>







          <div className="
            text-sm
            text-gray-400
            space-y-1
          ">


            <p>

              {formattedTime}

            </p>




            {
              event.venue && (

                <p>

                  {event.venue.name}

                  {
                    event.venue.city && (

                      <>
                        {' • '}
                        {event.venue.city}
                      </>

                    )
                  }


                  {
                    event.venue.country && (

                      <>
                        {' • '}
                        {event.venue.country}
                      </>

                    )
                  }


                </p>

              )
            }



          </div>








          <div className="
            mt-auto
            pt-5
            flex
            gap-3
            text-xs
            text-gray-400
          ">


            <span>

              ✓ {event.going_count ?? 0}

            </span>



            <span>

              ? {event.maybe_count ?? 0}

            </span>



            <span>

              ★ {event.went_count ?? 0}

            </span>


          </div>




        </div>


      </Card>


    </Link>

  );

}