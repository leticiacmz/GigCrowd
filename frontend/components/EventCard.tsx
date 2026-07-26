import Link from 'next/link';
import { format } from 'date-fns';
import Badge from './ui/Badge';
import Card from './ui/Card';

interface EventCardProps {
  event: {
    id: string;
    title: string;
    date: string;
    location: string;
    venue?: string;
    image?: string;
    artists?: Array<{
      name: string;
      slug?: string;
    }>;
  };
}

export default function EventCard({ event }: EventCardProps) {
  const formattedDate = format(new Date(event.date), 'MMM d, yyyy');
  
  return (
    <Link href={`/events/${event.id}`}>
      <Card hoverable className="p-0 overflow-hidden">
        {event.image && (
          <div className="aspect-video w-full">
            <img
              src={event.image}
              alt={event.title}
              className="w-full h-full object-cover"
            />
          </div>
        )}
        
        <div className="p-4">
          <div className="flex items-start justify-between mb-3">
            <div className="flex-1">
              <h3 className="text-foreground font-semibold text-lg mb-1 line-clamp-2">
                {event.title}
              </h3>
              <p className="text-gray-400 text-sm">
                {event.venue && `${event.venue} • `}{event.location}
              </p>
            </div>
            <Badge variant="accent" size="sm">
              {formattedDate}
            </Badge>
          </div>
          
          {event.artists && event.artists.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-3">
              {event.artists.slice(0, 3).map((artist, index) => (
                <Badge key={index} variant="outline" size="sm">
                  {artist.name}
                </Badge>
              ))}
              {event.artists.length > 3 && (
                <Badge variant="outline" size="sm">
                  +{event.artists.length - 3}
                </Badge>
              )}
            </div>
          )}
        </div>
      </Card>
    </Link>
  );
}
