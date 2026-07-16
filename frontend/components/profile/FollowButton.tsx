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


      const response =
        await followAPI.getStatus(
          username
        );



      setFollowing(
        response.following
      );



      onFollowChange?.(
        response.following
      );



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



      if (following) {


        await followAPI.unfollowUser(
          username
        );


        setFollowing(false);



        onFollowChange?.(
          false
        );



      } else {


        await followAPI.followUser(
          username
        );


        setFollowing(true);



        onFollowChange?.(
          true
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

    return (

      <button

        disabled

        className="
          px-5
          py-2
          rounded-lg
          bg-gray-700
          text-gray-400
        "

      >

        Loading...

      </button>

    );

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