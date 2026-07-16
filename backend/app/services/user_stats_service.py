from datetime import datetime, UTC


class UserStatsService:

    def __init__(
        self,
        user_repository,
        show_log_repository,
        db,
    ):

        self.user_repository = user_repository
        self.show_log_repository = show_log_repository
        self.db = db


    async def get_user_stats(
        self,
        username: str,
    ):

        user = await self.user_repository.get_by_username(
            username
        )


        if not user:

            return None


        user_id = str(
            user["_id"]
        )


        logs = await (
            self.show_log_repository.get_user_logs(
                user_id
            )
        )


        went = 0

        going = 0

        maybe = 0


        artists = set()


        for log in logs:

            status = log.get(
                "status"
            )


            if status == "went":

                went += 1


            elif status == "going":

                going += 1


            elif status == "maybe":

                maybe += 1



            event = await self.db.events.find_one(
                {
                    "_id": log.get(
                        "event_id"
                    )
                }
            )


            if event:

                artists.add(
                    event.get(
                        "artist_id"
                    )
                )



        posts = await self.db.posts.count_documents(
            {
                "user_id": user_id
            }
        )



        upcoming = await self.db.events.count_documents(
            {
                "_id":
                {
                    "$in":
                    [
                        log.get(
                            "event_id"
                        )
                        for log in logs
                        if log.get(
                            "status"
                        )
                        in [
                            "going",
                            "maybe",
                        ]
                    ]
                },

                "date":
                {
                    "$gte":
                    datetime.now(
                        UTC
                    )
                }
            }
        )



        return {

            "username":
                user.get(
                    "username"
                ),


            "followers_count":
                user.get(
                    "followers_count",
                    0,
                ),


            "following_count":
                user.get(
                    "following_count",
                    0,
                ),


            "shows_attended":
                went,


            "shows_going":
                going,


            "shows_maybe":
                maybe,


            "artists_seen":
                len(
                    artists
                ),


            "upcoming_events":
                upcoming,


            "total_posts":
                posts,
        }