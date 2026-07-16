'use client';


import {
  useEffect,
  useState
} from 'react';


import {
  useRouter
} from 'next/navigation';


import Link from 'next/link';


import {
  userAPI
} from '../lib/api';


import {
  User,
  UserStats
} from '../types/user';


import {
  logout
} from '../lib/auth';



export default function ProfilePage() {


  const router = useRouter();


  const [user, setUser] = useState<User | null>(
    null
  );


  const [stats, setStats] = useState<UserStats | null>(
    null
  );


  const [loading, setLoading] = useState(true);



  useEffect(() => {


    const token =
      localStorage.getItem(
        'token'
      );


    if (!token) {

      router.push(
        '/login'
      );

      return;
    }


    loadProfile();


  }, [router]);





  async function loadProfile() {


    try {


      const [
        userData,
        statsData
      ] = await Promise.all([

        userAPI.getMe(),

        userAPI.getMyStats()

      ]);



      setUser(
        userData
      );


      setStats(
        statsData
      );



    } catch(error) {


      console.error(
        'Failed loading profile',
        error
      );


    } finally {


      setLoading(false);

    }

  }




  function handleLogout() {


    logout();


    router.push(
      '/login'
    );

  }





  if (loading) {


    return (

      <div className="
        min-h-screen
        flex
        items-center
        justify-center
        text-gray-400
      ">

        Loading profile...

      </div>

    );

  }




  if (!user || !stats) {


    return (

      <div className="
        min-h-screen
        flex
        items-center
        justify-center
        text-gray-400
      ">

        Failed to load profile

      </div>

    );

  }





  return (


    <div className="
      min-h-screen
      bg-black
      text-white
    ">


      <header className="
        border-b
        border-gray-800
        px-6
        py-4
      ">


        <div className="
          max-w-5xl
          mx-auto
          flex
          justify-between
          items-center
        ">


          <Link
            href="/feed"
            className="
              text-2xl
              font-bold
              text-purple-500
            "
          >

            GigCrowd

          </Link>



          <nav className="
            flex
            gap-5
            text-gray-400
          ">


            <Link href="/feed">
              Feed
            </Link>


            <Link href="/events">
              Events
            </Link>


            <button
              onClick={handleLogout}
            >
              Logout
            </button>


          </nav>


        </div>


      </header>





      <main className="
        max-w-5xl
        mx-auto
        px-6
        py-8
      ">


        <section className="
          bg-gray-900
          border
          border-gray-800
          rounded-xl
          p-6
        ">



          <div className="
            flex
            gap-6
            items-center
          ">



            <div className="
              w-28
              h-28
              rounded-full
              bg-purple-600
              flex
              items-center
              justify-center
              text-4xl
              font-bold
            ">

              {
                user.username
                  .charAt(0)
                  .toUpperCase()
              }


            </div>




            <div>


              <h1 className="
                text-3xl
                font-bold
              ">

                {user.username}

              </h1>



              <p className="
                text-gray-400
              ">

                {user.email}

              </p>



              {
                user.bio &&

                <p className="
                  mt-3
                  text-gray-300
                ">

                  {user.bio}

                </p>

              }



            </div>



          </div>





          <div className="
            grid
            grid-cols-2
            md:grid-cols-4
            gap-4
            mt-8
          ">


            <StatCard
              label="Followers"
              value={stats.followers_count}
            />


            <StatCard
              label="Following"
              value={stats.following_count}
            />


            <StatCard
              label="Shows attended"
              value={stats.shows_attended}
            />


            <StatCard
              label="Artists seen"
              value={stats.artists_seen}
            />



          </div>



        </section>





        <section className="
          mt-6
          bg-gray-900
          border
          border-gray-800
          rounded-xl
          p-6
        ">


          <h2 className="
            text-xl
            font-bold
            mb-5
          ">

            Gig Stats

          </h2>



          <div className="
            grid
            grid-cols-2
            md:grid-cols-3
            gap-4
          ">


            <StatCard
              label="Upcoming concerts"
              value={stats.upcoming_events}
            />


            <StatCard
              label="Maybe concerts"
              value={stats.shows_maybe}
            />


            <StatCard
              label="Posts"
              value={stats.total_posts}
            />


          </div>



        </section>



      </main>


    </div>

  );

}





function StatCard(
  {
    label,
    value
  }:
  {
    label:string;
    value:number;
  }
) {


  return (

    <div className="
      bg-gray-800
      rounded-lg
      p-4
      text-center
    ">


      <div className="
        text-3xl
        font-bold
      ">

        {value}

      </div>


      <div className="
        text-sm
        text-gray-400
      ">

        {label}

      </div>


    </div>

  );

}