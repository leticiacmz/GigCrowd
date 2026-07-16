'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';

import { userAPI } from '@/app/lib/api';
import FollowButton from '@/components/profile/FollowButton';
import ProfileStats from '@/components/profile/ProfileStats';

import { format } from 'date-fns';


interface UserProfile {
  username: string;
  email: string;
  full_name?: string;
  bio?: string;
  location?: string;
  created_at: string;
}


interface ProfileStatsType {
  followers_count?: number;
  following_count?: number;

  shows_attended: number;
  shows_going: number;
  shows_maybe: number;
  artists_seen: number;
  upcoming_events: number;
  total_posts: number;
}


export default function ProfilePage() {

  const { username } = useParams<{ username: string }>();


  const [user, setUser] = useState<UserProfile | null>(null);
  const [stats, setStats] = useState<ProfileStatsType | null>(null);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);

  const [loading, setLoading] = useState(true);


  const [editing, setEditing] = useState(false);


  const [form, setForm] = useState({
    full_name: '',
    bio: '',
    location: ''
  });



  async function loadProfile() {

    try {

      try {
        const me = await userAPI.getMe();
        setCurrentUser(me);
      } catch {
        setCurrentUser(null);
      }


      const profile = await userAPI.getProfile(username);

      setUser(profile);


      setForm({
        full_name: profile.full_name || '',
        bio: profile.bio || '',
        location: profile.location || ''
      });



      const profileStats = await userAPI.getProfileStats(username);

      setStats(profileStats);


    } finally {

      setLoading(false);

    }

  }



  useEffect(() => {

    if(username){
      loadProfile();
    }

  }, [username]);




  async function handleSave() {

  if (!user) {
    return;
  }


  const response = await userAPI.updateMe(form);


  setUser({
    ...user,
    ...response.user,
  });


  setEditing(false);

}



  function handleCancel(){

    if(!user){
      return;
    }


    setForm({
      full_name: user.full_name || '',
      bio: user.bio || '',
      location: user.location || ''
    });


    setEditing(false);

  }





  if(loading){

    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400">
          Loading profile...
        </p>
      </div>
    );

  }




  if(!user){

    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400">
          User not found.
        </p>
      </div>
    );

  }




  const isOwnProfile =
    currentUser?.username === user.username;




  return (

    <div className="min-h-screen">


      <header className="border-b border-gray-800 px-4 py-4">

        <div className="max-w-5xl mx-auto flex justify-between items-center">


          <Link
            href="/feed"
            className="text-2xl font-bold bg-gradient-to-r from-purple-500 to-pink-500 bg-clip-text text-transparent"
          >
            GigCrowd
          </Link>



          <nav className="flex gap-4">

            <Link
              href="/feed"
              className="text-gray-400 hover:text-white"
            >
              Feed
            </Link>


            <Link
              href="/events"
              className="text-gray-400 hover:text-white"
            >
              Events
            </Link>

          </nav>


        </div>

      </header>





      <main className="max-w-5xl mx-auto px-4 py-8 space-y-8">



        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">



          <div className="flex justify-between items-start">


            <div className="flex gap-4">


              <div className="w-20 h-20 rounded-full bg-gray-800 flex items-center justify-center text-3xl font-bold">
                {user.username.charAt(0).toUpperCase()}
              </div>



              <div>

                <h1 className="text-3xl font-bold">
                  {user.username}
                </h1>


                <p className="text-gray-400">
                  {user.email}
                </p>

              </div>


            </div>





            {
              isOwnProfile ? (

                editing ? (

                  <div className="flex gap-2">

                    <button
                      onClick={handleSave}
                      className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg"
                    >
                      Save
                    </button>


                    <button
                      onClick={handleCancel}
                      className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg"
                    >
                      Cancel
                    </button>

                  </div>

                ) : (

                  <button
                    onClick={() => setEditing(true)}
                    className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg"
                  >
                    Edit Profile
                  </button>

                )


              ) : (

                <FollowButton username={user.username} />

              )

            }



          </div>





          <div className="flex gap-8 mt-6">


            <div>
              <p className="text-2xl font-bold">
                {stats?.followers_count ?? 0}
              </p>

              <p className="text-gray-400">
                Followers
              </p>

            </div>



            <div>

              <p className="text-2xl font-bold">
                {stats?.following_count ?? 0}
              </p>

              <p className="text-gray-400">
                Following
              </p>

            </div>


          </div>






          <div className="mt-6 space-y-3">


            {
              editing ? (

                <>


                  <input
                    value={form.full_name}
                    onChange={(e)=>
                      setForm({
                        ...form,
                        full_name:e.target.value
                      })
                    }
                    placeholder="Full name"
                    className="w-full bg-gray-800 rounded p-2"
                  />



                  <textarea
                    value={form.bio}
                    onChange={(e)=>
                      setForm({
                        ...form,
                        bio:e.target.value
                      })
                    }
                    placeholder="Bio"
                    className="w-full bg-gray-800 rounded p-2"
                  />



                  <input
                    value={form.location}
                    onChange={(e)=>
                      setForm({
                        ...form,
                        location:e.target.value
                      })
                    }
                    placeholder="Location"
                    className="w-full bg-gray-800 rounded p-2"
                  />



                </>


              ) : (

                <>


                  {
                    user.full_name &&
                    <p>
                      {user.full_name}
                    </p>
                  }


                  {
                    user.bio &&
                    <p className="text-gray-400">
                      {user.bio}
                    </p>
                  }


                  {
                    user.location &&
                    <p className="text-gray-400">
                      📍 {user.location}
                    </p>
                  }


                </>

              )

            }



            <p className="text-sm text-gray-500">

              Joined {
                format(
                  new Date(user.created_at),
                  'MMMM yyyy'
                )
              }

            </p>


          </div>


        </div>





        {
          stats &&
          <ProfileStats stats={stats}/>
        }



      </main>


    </div>

  );

}