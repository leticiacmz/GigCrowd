'use client';

import Link from 'next/link';


interface ProfileHeaderProps {

  user: {

    username: string;

    email?: string;

    full_name?: string;

    bio?: string;

    location?: string;

    avatar_url?: string;

    followers_count?: number;

    following_count?: number;

  };


  isOwner?: boolean;

  onEditClick?: () => void;

}



export default function ProfileHeader({

  user,

  isOwner = false,

  onEditClick,

}: ProfileHeaderProps) {



  return (

    <div
      className="
        bg-card-hover
        border
        border-border
        rounded-lg
        p-6
      "
    >



      <div
        className="
          flex
          items-start
          gap-6
        "
      >



        {/* Avatar */}

        <div
          className="
            w-24
            h-24
            bg-gradient-to-br
            from-purple-500
            to-pink-500
            rounded-full
            flex
            items-center
            justify-center
            text-white
            text-4xl
            font-bold
          "
        >

          {
            user.username
              ?.charAt(0)
              .toUpperCase()
          }


        </div>







        <div className="flex-1">



          <div
            className="
              flex
              justify-between
              items-start
            "
          >



            <div>


              <h1
                className="
                  text-2xl
                  font-bold
                "
              >

                @{user.username}


              </h1>




              {
                user.email && (

                  <p
                    className="
                      text-muted
                    "
                  >

                    {user.email}


                  </p>

                )
              }



            </div>








            {
              isOwner && (

                <button

                  onClick={onEditClick}

                  className="
                    px-4
                    py-2
                    bg-card-hover
                    hover:bg-card-hover
                    rounded-lg
                    transition-colors
                  "

                >

                  Edit Profile

                </button>

              )
            }



          </div>









          <div
            className="
              flex
              gap-8
              mt-5
            "
          >



            <div>


              <p
                className="
                  text-2xl
                  font-bold
                "
              >

                {
                  user.followers_count ?? 0
                }


              </p>


              <p
                className="
                  text-muted
                  text-sm
                "
              >

                Followers


              </p>


            </div>







            <div>


              <p
                className="
                  text-2xl
                  font-bold
                "
              >

                {
                  user.following_count ?? 0
                }


              </p>


              <p
                className="
                  text-muted
                  text-sm
                "
              >

                Following


              </p>


            </div>




          </div>





        </div>





      </div>









      {
        user.full_name && (

          <p
            className="
              mt-6
              text-foreground
            "
          >

            {user.full_name}


          </p>

        )
      }







      {
        user.bio && (

          <p
            className="
              mt-2
              text-muted
            "
          >

            {user.bio}


          </p>

        )
      }







      {
        user.location && (

          <p
            className="
              mt-2
              text-muted
            "
          >

            📍 {user.location}


          </p>

        )
      }





    </div>

  );

}