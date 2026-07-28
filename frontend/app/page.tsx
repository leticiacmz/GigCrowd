'use client';

import Link from 'next/link';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { isAuthenticated } from './lib/auth';

import Button from '../components/ui/Button';
import Card from '../components/ui/Card';


export default function Home() {

  const router = useRouter();


  useEffect(() => {

    if (isAuthenticated()) {

      router.replace('/feed');

    }

  }, [router]);



  return (

    <div className="
      min-h-[calc(100vh-4rem)]
      flex
      flex-col
      items-center
      px-4
      pt-2
      pb-8
    ">


      <section className="
        max-w-4xl
        text-center
      ">


        <h1 className="
          text-[72px]
          sm:text-[96px]
          font-black
          tracking-tight
          bg-gradient-to-r
          from-accent
          via-secondary
          to-accent
          bg-clip-text
          text-transparent
          drop-shadow-[0_0_6px_rgba(255,0,255,0.12)]
          mb-6
        ">

          GigCrowd

        </h1>



        <h2 className="
          text-3xl
          sm:text-4xl
          font-bold
          mb-5
        ">

          Every concert tells a story.

        </h2>



        <p className="
          text-gray-400
          text-lg
          max-w-xl
          mx-auto
          mb-10
        ">

          Discover artists, track live events,
          and share the concerts that become
          unforgettable memories.

        </p>


       <div
        className="
          flex
          justify-center
          gap-4
          flex-wrap
        "
      >

        <Link href="/events">

        <Button
          variant="neon"
          size="md"
          animated
        >
          Explore Events
        </Button>

      </Link>

        <Link href="/register">

        <Button
          variant="outlineGradient"
          size="md"
          animated
        >
          Join GigCrowd
        </Button>

      </Link>

      </div>


      </section>






      <section className="
        grid
        md:grid-cols-3
        gap-6
        max-w-5xl
        w-full
        mt-10
      ">



        <Card className="
          p-5
          text-center
          transition-all
          hover:border-accent
          hover:shadow-[0_0_20px_rgba(255,0,255,0.15)]
        ">


          <h3 className="
            text-lg
            font-bold
            mb-3
          ">

            Discover Artists

          </h3>


          <p className="
            text-sm
            leading-relaxed
            text-gray-400
          ">

            Find artists and explore
            upcoming live events.

          </p>


        </Card>





        <Card className="
          p-5
          text-center
          transition-all
          hover:border-secondary
          hover:shadow-[0_0_20px_rgba(0,255,255,0.15)]
        ">


          <h3 className="
            text-lg
            font-bold
            mb-3
          ">

            Track Shows

          </h3>


          <p className="
            text-sm
            leading-relaxed
            text-gray-400
          ">

            Save concerts you attended
            or want to experience.

          </p>


        </Card>





        <Card className="
          p-5
          text-center
          transition-all
          hover:border-accent
          hover:shadow-[0_0_20px_rgba(255,0,255,0.15)]
        ">


          <h3 className="
            text-lg
            font-bold
            mb-3
          ">

            Share Stories

          </h3>


          <p className="
            text-sm
            leading-relaxed
            text-gray-400
          ">

            Turn every concert into
            a memory worth sharing.

          </p>


        </Card>


      </section>



    </div>

  );

}