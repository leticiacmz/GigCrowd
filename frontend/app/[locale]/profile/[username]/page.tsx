'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useParams } from 'next/navigation';
import Link from 'next/link';

import { userAPI } from '@/app/lib/api';
import { isAuthenticated } from '@/app/lib/auth';
import { useAuthAction } from '@/app/lib/use-auth-action';
import FollowButton from '@/components/profile/FollowButton';
import ProfileStats from '@/components/profile/ProfileStats';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import Card from '@/components/ui/Card';
import Avatar from '@/components/ui/Avatar';
import LoadingState from '@/components/LoadingState';

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

  const { username, locale: localeParam } = useParams<{
    username: string;
    locale: string;
  }>();
  const locale = localeParam || 'en';
  const t = useTranslations('profile');

  const runAuthAction = useAuthAction({ locale });


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

      // `getMe` is a protected endpoint. Public profiles stay viewable
      // while signed out, so the session is only requested when one exists.
      if (isAuthenticated()) {

        try {
          const me = await userAPI.getMe();
          setCurrentUser(me);
        } catch {
          setCurrentUser(null);
        }

      } else {

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


  // Editing a profile is a session-bound mutation.
  await runAuthAction(async () => {

  const response = await userAPI.updateMe(form);


  setUser({
    ...user,
    ...response.user,
  });


  setEditing(false);

  });

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
        <LoadingState message="Loading profile..." />
      </div>
    );

  }




  if(!user){

    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400">{t('notFound')}</p>
      </div>
    );

  }




  const isOwnProfile =
    currentUser?.username === user.username;




  return (

    <div className="min-h-screen">


      <main className="max-w-5xl mx-auto px-4 py-8 space-y-8">



        <Card className="p-6">



          <div className="flex justify-between items-start">


            <div className="flex gap-4">


              <Avatar
                src={undefined}
                fallback={user.username.charAt(0).toUpperCase()}
                size="lg"
              />



              <div>

                <h1 className="text-[28px] font-bold">
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

                    <Button
                      onClick={handleSave}
                      variant="primary"
                    >{t('saveChanges')}</Button>


                    <Button
                      onClick={handleCancel}
                      variant="outline"
                    >{t('cancel')}</Button>

                  </div>

                ) : (

                  <Button
                    onClick={() => setEditing(true)}
                    variant="outline"
                  >{t('editProfile')}</Button>

                )


              ) : (

                <FollowButton username={user.username} />

              )

            }



          </div>





          <div className="flex gap-8 mt-6">


            <div>
              <p className="text-[24px] font-bold">
                {stats?.followers_count ?? 0}
              </p>

              <p className="text-gray-400">{t('followers')}</p>

            </div>



            <div>

              <p className="text-[24px] font-bold">
                {stats?.following_count ?? 0}
              </p>

              <p className="text-gray-400">{t('following')}</p>

            </div>


          </div>






          <div className="mt-6 space-y-3">


            {
              editing ? (

                <>


                  <Input
                    value={form.full_name}
                    onChange={(e)=>
                      setForm({
                        ...form,
                        full_name:e.target.value
                      })
                    }
                    placeholder="Full name"
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
                    className="w-full bg-card-bg border border-border rounded-lg p-3 text-foreground"
                    rows={3}
                  />



                  <Input
                    value={form.location}
                    onChange={(e)=>
                      setForm({
                        ...form,
                        location:e.target.value
                      })
                    }
                    placeholder="Location"
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


        </Card>





        {
          stats &&
          <ProfileStats stats={stats}/>
        }



      </main>


    </div>

  );

}