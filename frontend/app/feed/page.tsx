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
  feedAPI,
  userAPI,
} from '../lib/api';

import {
  format,
} from 'date-fns';



interface Activity {

  id: string;

  user: {

    id: string;

    username: string;

    avatar_url?: string;

  };


  activity_type: string;

  target_id?: string;

  target_type?: string;

  metadata?: any;

  created_at: string;

  event?: any;

  post?: any;

}





export default function FeedPage() {


  const router = useRouter();


  const [
    activities,
    setActivities,
  ] = useState<Activity[]>([]);



  const [
    loading,
    setLoading,
  ] = useState(true);



  const [
    currentUser,
    setCurrentUser,
  ] = useState<any>(null);






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



    loadFeed();

    loadCurrentUser();


  }, [router]);









  async function loadFeed() {


    try {


      const data =
        await feedAPI.getFeed();



      setActivities(
        data
      );



    } catch(error) {


      console.error(
        'Failed to load feed:',
        error
      );



    } finally {


      setLoading(false);


    }


  }








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








  function handleLogout() {


    localStorage.removeItem(
      'token'
    );


    localStorage.removeItem(
      'user'
    );


    router.push(
      '/login'
    );


  }








  function getActivityText(
    activity: Activity
  ) {


    const username =
      activity.user.username;



    switch(
      activity.activity_type
    ) {


      case 'follow':

        return `${username} started following someone`;



      case 'attend_event':

        const status =
          activity.metadata?.status ||
          'going';


        return `${username} is ${status} to an event`;



      case 'create_post':

        return `${username} created a post`;



      case 'like_post':

        return `${username} liked a post`;



      default:

        return `${username} did something`;


    }


  }









  return (

    <div className="min-h-screen">


      <header
        className="
          border-b
          border-gray-800
          px-4
          py-4
        "
      >


        <div
          className="
            max-w-4xl
            mx-auto
            flex
            items-center
            justify-between
          "
        >


          <Link

            href="/"

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





          <nav
            className="
              flex
              items-center
              gap-4
            "
          >


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
              className="text-gray-400 hover:text-white transition-colors"
            >
              Profile
            </Link>





            <button

              onClick={
                handleLogout
              }

              className="
                text-gray-400
                hover:text-white
              "

            >

              Logout

            </button>



          </nav>


        </div>


      </header>









      <main
        className="
          max-w-4xl
          mx-auto
          px-4
          py-8
        "
      >


        <h1
          className="
            text-3xl
            font-bold
            mb-6
          "
        >

          Your Feed

        </h1>







        {
          loading ? (


            <div
              className="
                text-center
                py-12
              "
            >

              <p className="text-gray-400">

                Loading feed...

              </p>


            </div>



          ) : activities.length === 0 ? (



            <div
              className="
                text-center
                py-12
              "
            >


              <p
                className="
                  text-gray-400
                  mb-4
                "
              >

                No activity yet.

              </p>



              <p
                className="
                  text-gray-500
                "
              >

                Follow some users to see their activity here!

              </p>



            </div>



          ) : (



            <div
              className="
                space-y-4
              "
            >


              {
                activities.map(
                  (
                    activity
                  ) => (


                    <div

                      key={
                        activity.id
                      }

                      className="
                        bg-gray-900
                        border
                        border-gray-800
                        rounded-lg
                        p-4
                      "

                    >


                      <div
                        className="
                          flex
                          items-start
                          gap-4
                        "
                      >



                        <Link

                          href={
                            `/profile/${activity.user.username}`
                          }

                        >

                          <div
                            className="
                              w-10
                              h-10
                              bg-gradient-to-br
                              from-purple-500
                              to-pink-500
                              rounded-full
                              flex
                              items-center
                              justify-center
                              text-white
                              font-bold
                            "
                          >

                            {
                              activity.user.username
                                .charAt(0)
                                .toUpperCase()
                            }


                          </div>


                        </Link>






                        <div
                          className="
                            flex-1
                          "
                        >


                          <p
                            className="
                              text-gray-300
                              mb-2
                            "
                          >


                            <Link

                              href={
                                `/profile/${activity.user.username}`
                              }

                              className="
                                font-semibold
                                hover:text-purple-400
                              "

                            >

                              @{activity.user.username}

                            </Link>


                            {' '}
                            
                            {
                              getActivityText(
                                activity
                              )
                              .replace(
                                activity.user.username,
                                ''
                              )
                            }


                          </p>







                          {
                            activity.event && (


                              <div
                                className="
                                  bg-gray-800
                                  rounded-lg
                                  p-3
                                "
                              >


                                <h3
                                  className="
                                    font-semibold
                                  "
                                >

                                  {
                                    activity.event.title
                                  }

                                </h3>



                                <p
                                  className="
                                    text-sm
                                    text-gray-400
                                  "
                                >

                                  {
                                    format(
                                      new Date(
                                        activity.event.date
                                      ),
                                      'MMM d, yyyy'
                                    )
                                  }

                                  {' • '}

                                  {
                                    activity.event.location
                                  }

                                </p>


                              </div>


                            )
                          }







                          {
                            activity.post && (


                              <div
                                className="
                                  bg-gray-800
                                  rounded-lg
                                  p-3
                                "
                              >



                                {
                                  activity.post.content && (


                                    <p
                                      className="
                                        text-gray-300
                                      "
                                    >

                                      {
                                        activity.post.content
                                      }


                                    </p>


                                  )

                                }





                                {
                                  activity.post.media_url && (


                                    <img

                                      src={
                                        activity.post.media_url
                                      }

                                      alt="Post media"

                                      className="
                                        mt-2
                                        rounded-lg
                                        max-w-full
                                      "

                                    />


                                  )
                                }


                              </div>


                            )
                          }







                          <p
                            className="
                              text-xs
                              text-gray-500
                              mt-2
                            "
                          >

                            {
                              format(
                                new Date(
                                  activity.created_at
                                ),
                                'MMM d, yyyy • h:mm a'
                              )
                            }


                          </p>


                        </div>


                      </div>


                    </div>


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