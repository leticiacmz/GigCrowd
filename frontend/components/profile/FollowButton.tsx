'use client';

import {
  useEffect,
  useState,
} from 'react';

import {
  followAPI,
} from '@/app/lib/api';



interface FollowButtonProps {

  username: string;

  onFollowChange?: (
    following: boolean
  ) => void;

}





export default function FollowButton({

  username,

  onFollowChange,

}: FollowButtonProps) {



  const [
    following,
    setFollowing,
  ] = useState(false);



  const [
    loading,
    setLoading,
  ] = useState(true);







  useEffect(() => {

    loadFollowStatus();

  }, [username]);








  async function loadFollowStatus() {


    try {


      const status =
        await followAPI.getStatus(
          username
        );



      setFollowing(
        status.following
      );



      if (onFollowChange) {

        onFollowChange(
          status.following
        );

      }



    } catch(error) {


      console.error(
        'Failed to load follow status:',
        error
      );



    } finally {


      setLoading(false);


    }


  }








  async function handleFollow() {


    try {


      setLoading(true);



      let newStatus = false;



      if (following) {


        await followAPI.unfollowUser(
          username
        );


        newStatus = false;



      } else {


        await followAPI.followUser(
          username
        );


        newStatus = true;


      }



      setFollowing(
        newStatus
      );



      if (onFollowChange) {


        onFollowChange(
          newStatus
        );


      }



    } catch(error) {


      console.error(
        'Failed to update follow:',
        error
      );



    } finally {


      setLoading(false);


    }


  }








  if (loading) {

    return null;

  }








  return (

    <button

      onClick={
        handleFollow
      }

      className="
        px-5
        py-2
        rounded-lg
        bg-purple-600
        hover:bg-purple-700
        text-white
        transition-colors
      "

    >

      {
        following
          ? 'Following'
          : 'Follow'
      }


    </button>

  );

}