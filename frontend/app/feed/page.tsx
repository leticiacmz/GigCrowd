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

import LoadingState from '../../components/LoadingState';
import EmptyState from '../../components/EmptyState';
import Avatar from '../../components/ui/Avatar';
import Card from '../../components/ui/Card';



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
            text-[28px]
            font-bold
            mb-6
          "
        >

          Your Feed

        </h1>







        {
          loading ? (


            <LoadingState message="Loading feed..." />



          ) : activities.length === 0 ? (



            <EmptyState
              icon="🎵"
              title="No activity yet"
              description="Follow some users to see their activity here!"
            />



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


                    <Card
                      key={activity.id}
                    >


                      <div
                        className="
                          flex
                          items-start
                          gap-4
                        "
                      >



                        <Link
                          href={`/profile/${activity.user.username}`}
                        >
                          <Avatar
                            src={activity.user.avatar_url}
                            fallback={activity.user.username.charAt(0).toUpperCase()}
                            size="md"
                          />
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
                                hover:text-accent
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
                                  bg-card-hover
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
                                  bg-card-hover
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


                    </Card>


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