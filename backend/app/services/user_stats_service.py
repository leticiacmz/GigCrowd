from datetime import datetime, UTC


class UserStatsService:


    def __init__(
        self,
        user_repository,
        show_log_repository,
        db
    ):

        self.user_repository = user_repository

        self.show_log_repository = show_log_repository

        self.db = db



    async def get_user_stats(
        self,
        user_id: str
    ):


        user_stats = await (
            self.user_repository.get_stats(
                user_id
            )
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
                    "_id":
                    log.get("event_id")
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
                        log.get("event_id")
                        for log in logs
                        if log.get("status")
                        in [
                            "going",
                            "maybe"
                        ]
                    ]
                },

                "date":
                {
                    "$gte":
                    datetime.now(UTC)
                }
            }
        )


        return {

            **user_stats,


            "shows_attended":
                went,


            "shows_going":
                going,


            "shows_maybe":
                maybe,


            "artists_seen":
                len(artists),


            "upcoming_events":
                upcoming,


            "total_posts":
                posts
        }