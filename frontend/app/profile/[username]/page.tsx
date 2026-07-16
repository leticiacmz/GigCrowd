'use client';

import {
  useEffect,
  useState,
} from 'react';

import {
  useParams,
  useRouter,
} from 'next/navigation';

import Link from 'next/link';

import {
  userAPI,
} from '@/app/lib/api';

import FollowButton from '@/components/profile/FollowButton';

import { format } from 'date-fns';



export default function ProfilePage() {


  const params = useParams();

  const router = useRouter();


  const username =
    params.username as string;



  const [
    user,
    setUser,
  ] = useState<any>(null);



  const [
    stats,
    setStats,
  ] = useState<any>(null);



  const [
    currentUser,
    setCurrentUser,
  ] = useState<any>(null);



  const [
    loading,
    setLoading,
  ] = useState(true);



  const [
    editing,
    setEditing,
  ] = useState(false);



  const [
    formData,
    setFormData,
  ] = useState({

    full_name: '',
    bio: '',
    location: '',

  });






  useEffect(() => {

    loadProfile();

  }, [username]);







  async function loadProfile() {


    try {


      const loggedUser =
        await userAPI.getMe();



      setCurrentUser(
        loggedUser
      );



      const profile =
        await userAPI.getProfile(
          username
        );



      const profileStats =
        await userAPI.getProfileStats(
          username
        );



      setUser(
        profile
      );


      setStats(
        profileStats
      );



      setFormData({

        full_name:
          profile.full_name || '',

        bio:
          profile.bio || '',

        location:
          profile.location || '',

      });



    } catch(error) {


      console.error(
        'Failed to load profile:',
        error
      );


    } finally {


      setLoading(false);


    }


  }








  async function handleUpdate() {


    try {


      await userAPI.updateMe(
        formData
      );


      await loadProfile();


      setEditing(false);



    } catch(error) {


      console.error(
        'Failed to update profile:',
        error
      );


    }


  }






  const isOwnProfile =
    currentUser?.username === username;








  if (loading) {

    return (

      <div className="
        min-h-screen
        flex
        items-center
        justify-center
      ">

        <p className="text-gray-400">
          Loading profile...
        </p>

      </div>

    );

  }







  if (!user) {

    return (

      <div className="
        min-h-screen
        flex
        items-center
        justify-center
      ">

        <p className="text-gray-400">
          User not found
        </p>

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
          max-w-4xl
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
              bg-gradient-to-r
              from-purple-500
              to-pink-500
              bg-clip-text
              text-transparent
            "
          >

            GigCrowd

          </Link>



          <Link
            href="/feed"
            className="
              text-gray-400
              hover:text-white
            "
          >

            Feed

          </Link>


        </div>

      </header>






      <main className="
        max-w-4xl
        mx-auto
        px-4
        py-8
      ">



        <div className="
          bg-gray-900
          border
          border-gray-800
          rounded-lg
          p-6
        ">



          <div className="
            flex
            justify-between
            items-start
          ">


            <div>

              <h1 className="
                text-3xl
                font-bold
              ">

                {user.username}

              </h1>


              <p className="text-gray-400">
                {user.email}
              </p>


            </div>





            {isOwnProfile ? (

              <button

                onClick={() =>
                  setEditing(!editing)
                }

                className="
                  px-4
                  py-2
                  bg-gray-800
                  rounded-lg
                  hover:bg-gray-700
                "

              >

                {
                  editing
                    ? 'Cancel'
                    : 'Edit Profile'
                }


              </button>


            ) : (

              <FollowButton
                username={username}
              />

            )}


          </div>





          <div className="
            flex
            gap-8
            mt-6
          ">


            <div>

              <p className="text-2xl font-bold">
                {stats?.followers_count || 0}
              </p>

              <p className="text-gray-400">
                Followers
              </p>

            </div>



            <div>

              <p className="text-2xl font-bold">
                {stats?.following_count || 0}
              </p>

              <p className="text-gray-400">
                Following
              </p>

            </div>



          </div>





          {
            editing && (

              <div className="
                mt-6
                space-y-4
              ">


                <input

                  value={
                    formData.full_name
                  }

                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      full_name:
                        e.target.value
                    })
                  }

                  className="
                    w-full
                    bg-gray-800
                    p-2
                    rounded
                  "

                  placeholder="Full name"

                />



                <textarea

                  value={
                    formData.bio
                  }

                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      bio:
                        e.target.value
                    })
                  }

                  className="
                    w-full
                    bg-gray-800
                    p-2
                    rounded
                  "

                  placeholder="Bio"

                />



                <button

                  onClick={
                    handleUpdate
                  }

                  className="
                    px-5
                    py-2
                    bg-purple-600
                    rounded
                  "

                >

                  Save

                </button>



              </div>

            )
          }






          {
            !editing && (

              <div className="
                mt-6
              ">


                {
                  user.full_name &&
                  <p>
                    {user.full_name}
                  </p>
                }



                {
                  user.bio &&
                  <p className="text-gray-400 mt-2">
                    {user.bio}
                  </p>
                }



                {
                  user.location &&
                  <p className="text-gray-400 mt-2">
                    📍 {user.location}
                  </p>
                }



                <p className="
                  text-gray-500
                  text-sm
                  mt-4
                ">

                  Joined {
                    format(
                      new Date(
                        user.created_at
                      ),
                      'MMMM yyyy'
                    )
                  }

                </p>


              </div>

            )
          }



        </div>


      </main>


    </div>

  );

}