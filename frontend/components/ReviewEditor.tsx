'use client';

import {
  useEffect,
  useState,
} from 'react';

import Button from './ui/Button';



interface ReviewEditorProps {

  initialRating: number;

  initialReview: string;

  loading: boolean;

  onSave: (
    data:{
      rating:number;
      review:string;
    }
  ) => Promise<void>;

  onDelete:()=>Promise<void>;

}







export default function ReviewEditor({

  initialRating = 0,

  initialReview = '',

  loading: externalLoading,

  onSave,

  onDelete,

}: ReviewEditorProps) {


  const [
    rating,
    setRating,
  ] = useState(initialRating);



  const [
    review,
    setReview,
  ] = useState(initialReview);



  const [
    editing,
    setEditing,
  ] = useState(
    !initialReview
  );



  const [
    loading,
    setLoading,
  ] = useState(false);







  useEffect(()=>{


    setRating(
      initialRating
    );


    setReview(
      initialReview
    );


    setEditing(
      !initialReview
    );


  },[
    initialRating,
    initialReview,
  ]);









  async function handleSave(){


    if(
      rating === 0
    ){

      return;

    }


    try{


      setLoading(true);


      await onSave({

        rating,

        review,

      });


      setEditing(false);


    }finally{


      setLoading(false);


    }


  }









  async function handleDelete(){


    try{


      setLoading(true);


      await onDelete();


      setRating(0);

      setReview('');

      setEditing(true);


    }finally{


      setLoading(false);


    }


  }









  function renderStars(){


    return (

      <div
        className="
          flex
          gap-1
        "
      >

        {
          [1,2,3,4,5].map(
            star => (

              <button

                key={star}

                type="button"

                onClick={() =>
                  setRating(star)
                }

                className="
                  text-2xl
                  transition
                  hover:scale-105
                "

              >

                <span

                  className={`
                    bg-gradient-to-r
                    from-pink-500
                    via-purple-500
                    to-cyan-400

                    bg-clip-text
                    text-transparent

                    transition

                    ${
                      star <= rating
                      ?
                      'opacity-100'
                      :
                      'opacity-35 hover:opacity-80'
                    }
                  `}

                >

                  {
                    star <= rating
                    ?
                    '★'
                    :
                    '☆'
                  }

                </span>


              </button>

            )
          )
        }

      </div>

    );


  }









  /*
    REVIEW SALVO
  */

  if(
    initialReview &&
    !editing
  ){

    return (

      <div
        className="
          space-y-4
        "
      >

        {renderStars()}


        <p
          className="
            text-gray-300
            leading-relaxed
          "
        >

          {initialReview}

        </p>




        <button

          type="button"

          onClick={() =>
            setEditing(true)
          }

          className="
            text-sm
            font-medium

            bg-gradient-to-r
            from-pink-500
            via-purple-500
            to-cyan-400

            bg-clip-text
            text-transparent

            hover:opacity-80

            transition
          "

        >

          Edit review

        </button>



      </div>

    );


  }









  /*
    FORMULÁRIO
  */

  return (

    <div
      className="
        space-y-5
      "
    >


      {renderStars()}







      {
        initialReview && editing && (

          <div
            className="
              flex
              justify-end
            "
          >

            <button

              type="button"

              onClick={() =>
                setEditing(false)
              }

              className="
                text-xs
                font-medium

                bg-gradient-to-r
                from-pink-500
                via-purple-500
                to-cyan-400

                bg-clip-text
                text-transparent

                hover:opacity-80

                transition
              "

            >

              Cancel

            </button>


          </div>

        )
      }









      <textarea

        value={review}

        onChange={
          event =>
            setReview(
              event.target.value
            )
        }


        placeholder="Share your experience about this show..."


        className="
          w-full

          min-h-[130px]

          rounded-lg

          p-4

          bg-[#111111]

          border
          border-border

          text-white

          placeholder:text-gray-500

          focus:outline-none

          focus:border-purple-500

          focus:ring-1

          focus:ring-purple-500

          resize-none

          transition
        "

      />









      <div
        className="
          flex
          justify-end
          items-center
          gap-4
        "
      >






        <Button

          variant="outline"

          disabled={
            loading ||
            externalLoading ||
            rating === 0
          }

          onClick={handleSave}

          className="
  !px-4
  !py-1.5
  !text-sm
  !rounded-md

  border
  border-purple-500

  bg-transparent

  bg-gradient-to-r
  from-pink-500
  via-purple-500
  to-cyan-400

  bg-clip-text
  text-transparent

  hover:scale-105
  transition-transform
"

        >

          {
            loading || externalLoading
            ?
            'Saving...'
            :
            initialReview
            ?
            'Save changes'
            :
            'Save review'
          }


        </Button>








        {
          initialReview && (

            <button

              type="button"

              onClick={handleDelete}

              disabled={
                loading ||
                externalLoading
              }

              className="
                text-xs
                font-medium

                bg-gradient-to-r
                from-pink-500
                via-purple-500
                to-cyan-400

                bg-clip-text
                text-transparent

                hover:opacity-80

                transition
              "

            >

              Delete review

            </button>

          )
        }





      </div>





    </div>

  );

}