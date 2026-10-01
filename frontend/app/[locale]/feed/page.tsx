'use client';

import {
  useEffect,
  useState,
  useCallback,
} from 'react';

import {
  useRouter,
  useParams,
} from 'next/navigation';

import RequireAuth from '../../../components/auth/RequireAuth';

import Link from 'next/link';

import {
  feedAPI,
  userAPI,
} from '../../lib/api';

import { logout } from '../../lib/auth';

import {
  format,
} from 'date-fns';

import LoadingState from '../../../components/LoadingState';
import EmptyState from '../../../components/EmptyState';
import Avatar from '../../../components/ui/Avatar';
import Card from '../../../components/ui/Card';
import Button from '../../../components/ui/Button';
import { useTranslations } from 'next-intl';



const PAGE_SIZE = 10;


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



function FeedContent() {
  const router = useRouter();
  const params = useParams();
  const locale = (params?.locale as string) || 'en';
  const t = useTranslations('feed');
  const tCommon = useTranslations('common');
  const tActivity = useTranslations('feed.activityTypes');


  const [
    activities,
    setActivities,
  ] = useState<Activity[]>([]);


  const [
    loading,
    setLoading,
  ] = useState(true);


  const [
    loadingMore,
    setLoadingMore,
  ] = useState(false);


  const [
    error,
    setError] = useState<string | null>(null);


  const [
    currentFilter,
    setCurrentFilter] = useState('all');


  const [
    hasMore,
    setHasMore
  ] = useState(false);


  const [
    currentUser,
    setCurrentUser,
  ] = useState<any>(null);

  const FILTERS = [
    { key: 'all', label: t('allActivity') },
    { key: 'attend_event', label: t('events') },
    { key: 'create_post', label: t('posts') },
    { key: 'follow', label: t('follows') },
    { key: 'like_post', label: t('likes') },
  ];

  const loadFeed = useCallback(
    async (
      filter: string,
      skip: number = 0,
      append: boolean = false,
    ) => {

      if (!append) {

        setLoading(true);

        setError(null);

      } else {

        setLoadingMore(true);

      }


      try {

        const params: any = {
          skip,
          limit: PAGE_SIZE,
        };

        if (filter !== 'all') {

          params.activity_type = filter;

        }


        const data =
          await feedAPI.getFeed(params);


        if (append) {

          setActivities(
            (prev) => [
              ...prev,
              ...data,
            ]
          );

        } else {

          setActivities(data);

        }


        setHasMore(
          data.length === PAGE_SIZE
        );


      } catch(err) {

        console.error(
          'Failed to load feed:',
          err
        );

        setError(
          t('errorLoading')
        );


      } finally {

        setLoading(false);

        setLoadingMore(false);

      }

    },
    []
  );


  useEffect(() => {


    loadFeed(currentFilter);

    loadCurrentUser();


  }, []);


  useEffect(() => {

    loadFeed(currentFilter);

  }, [currentFilter, loadFeed]);


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


    // Uses the shared logout helper so the auth-changed event fires and
    // any active route guard reacts, then returns to the localized home.
    logout();


    router.push(
      `/${locale}`
    );


  }


  function handleLoadMore() {

    loadFeed(
      currentFilter,
      activities.length,
      true,
    );

  }


  function handleRetry() {

    loadFeed(
      currentFilter,
      0,
      false,
    );

  }


  function handleFilterChange(
    filter: string
  ) {

    setCurrentFilter(filter);

    setActivities([]);

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

        return tActivity('follow');


      case 'attend_event':

        const status =
          activity.metadata?.status ||
          'going';

        return tActivity('attend_event');


      case 'create_post':

        return tActivity('create_post');


      case 'like_post':

        return tActivity('like_post');


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

          {t('title')}

        </h1>


        <div
          className="
            flex
            gap-2
            mb-6
            flex-wrap
          "
        >

          {FILTERS.map(
            (filter) => (
              <Button
                key={filter.key}
                variant={
                  currentFilter === filter.key
                    ? 'primary'
                    : 'ghost'
                }
                size="sm"
                onClick={() =>
                  handleFilterChange(
                    filter.key
                  )
                }
              >
                {filter.label}
              </Button>
            )
          )}

        </div>


        {error && (

          <div
            className="
              mb-4
              rounded-lg
              bg-red-500/20
              border
              border-red-500
              p-4
              text-center
            "
          >

            <p className="text-red-300 mb-3">
              {error}
            </p>

            <Button
              variant="outline"
              size="sm"
              onClick={handleRetry}
            >
              {tCommon('retry')}
            </Button>

          </div>

        )}


        {
          loading ? (


            <LoadingState message={t('loading')} />


          ) : activities.length === 0 && !error ? (


            <EmptyState
              icon="🎵"
              title={t('noActivity')}
              description={t('followUsers')}
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


              {hasMore && (

                <div className="text-center pt-4">

                  <Button
                    variant="outline"
                    onClick={handleLoadMore}
                    disabled={loadingMore}
                  >
                    {loadingMore ? t('loading') : t('loadMore')}
                  </Button>

                </div>

              )}

            </div>

          )
        }


      </main>


    </div>

  );


}


/**
 * The feed is personalized, so it requires a session. Signed-out visitors
 * are sent to the localized home page.
 */
export default function FeedPage() {

  const params = useParams();

  const locale =
    (params?.locale as string) || 'en';


  return (
    <RequireAuth locale={locale}>
      <FeedContent />
    </RequireAuth>
  );

}
