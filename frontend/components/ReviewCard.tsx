import Card from './ui/Card';
import Button from './ui/Button';


interface Props {

  rating:number;

  review:string;

  onEdit:()=>void;

}



export default function ReviewCard({
  rating,
  review,
  onEdit,
}:Props){


  return (

    <Card className="p-5 space-y-4">


      <div className="
        text-yellow-400
        text-xl
      ">

        {"★".repeat(rating)}

      </div>


      <p className="
        text-gray-200
        leading-relaxed
      ">

        {review}

      </p>



      <button
        
        onClick={onEdit}

        className="
          text-sm
          text-accent
          hover:underline
        "

      >

        Edit review

      </button>


    </Card>

  );


}