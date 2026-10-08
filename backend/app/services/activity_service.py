"""Activity and notification persistence.

`activities` is the single stream that powers the unified Feed timeline.
`notifications` is a separate, recipient-scoped stream that powers the
Notifications page: it is written by real backend actions and is never a
copy of the feed.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Iterable, Optional

from bson import ObjectId

from app.database.connection import get_database
from app.models.activity import (
    ActivityCreate,
    ActivityInDB,
    ActivityType,
    NotificationResponse,
    NotificationType,
)
from app.utils.ids import object_id_variants, to_object_id

logger = logging.getLogger(__name__)


# Feed filter -> the activity types that belong to it. Every category maps to
# real activity types so the filter never returns placeholder content.
#
# `follow` is deliberately absent from every category. A follow decides what a
# reader is eligible to see; it is not something they asked to read, and rendering
# "Ana followed Bruno" as a card turns the timeline into a list of relationships
# nobody chose to publish. Follows are still recorded, still notified, and still
# decide visibility - they are just never content.
#
# `attendance` is the name a reader recognises for what used to be called `events`;
# the old name is kept as an alias so a bookmark or a habit does not break.
#
# `following` is not an activity type: it is the same timeline scoped to the
# relationships the reader chose - the people they follow and the artist
# communities they follow - so it holds every kind of content, from whoever
# they follow. See `get_feed_activities` for how the scope is expressed.
FEED_CATEGORIES: dict[str, tuple[ActivityType, ...]] = {
    "all": (),
    "community": (
        ActivityType.CREATE_COMMUNITY_POST,
        ActivityType.COMMENT_POST,
        ActivityType.LIKE_POST,
    ),
    "reviews": (ActivityType.CREATE_REVIEW,),
    "attendance": (ActivityType.ATTEND_EVENT,),
    "events": (ActivityType.ATTEND_EVENT,),
    "following": (),
}

# Activity types that may never appear on the timeline, whatever was asked for.
#
# Enforced as a subtraction from the query rather than by simply leaving `follow`
# out of every category above, because a category added later would otherwise
# reintroduce it without anybody deciding to.
FEED_EXCLUDED_TYPES: tuple[ActivityType, ...] = (
    ActivityType.FOLLOW,
)

# Collection each activity type points at through `target_type`.
#
# A follow is deliberately absent: its target is a person, and a person is
# only ever exposed as a public profile, so it is resolved by its own
# projected lookup instead of the generic document loader below.
ACTIVITY_TARGET_COLLECTIONS: dict[str, str] = {
    ActivityType.CREATE_COMMUNITY_POST.value: "community_posts",
    ActivityType.COMMENT_POST.value: "comments",
    ActivityType.LIKE_POST.value: "community_posts",
    ActivityType.CREATE_REVIEW.value: "show_logs",
    ActivityType.ATTEND_EVENT.value: "show_logs",
    ActivityType.CREATE_POST.value: "posts",
}


class ActivityService:
    # =====================================================
    # ACTIVITIES
    # =====================================================

    @staticmethod
    async def create_activity(
        user_id: str,
        activity_data: ActivityCreate,
    ) -> ActivityInDB:
        """Persist a single activity for the unified feed."""
        db = get_database()

        activity_dict = activity_data.model_dump(mode="json")
        activity_dict["user_id"] = str(user_id)
        activity_dict["created_at"] = datetime.now(UTC)

        result = await db.activities.insert_one(activity_dict)
        activity_dict["_id"] = str(result.inserted_id)

        return ActivityInDB(**activity_dict)

    @staticmethod
    async def record(
        user_id: str,
        activity_type: ActivityType,
        *,
        target_id: Optional[str] = None,
        target_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Record an activity without letting bookkeeping break the request.

        Feed bookkeeping is secondary to the action the user actually asked
        for, so a failure here is logged and swallowed.
        """
        try:
            await ActivityService.create_activity(
                user_id,
                ActivityCreate(
                    activity_type=activity_type,
                    target_id=target_id,
                    target_type=target_type,
                    metadata=metadata,
                ),
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to record activity %s", activity_type)

    # =====================================================
    # FEED
    # =====================================================

    @staticmethod
    async def _get_followed_user_ids(db, user_id: str) -> list[str]:
        follows = await db.follows.find(
            {"follower_id": {"$in": object_id_variants(user_id)}}
        ).to_list(length=1000)

        return [str(follow["following_id"]) for follow in follows]

    @staticmethod
    async def _get_followed_artist_slugs(db, user_id: str) -> list[str]:
        follows = await db.artist_follows.find(
            {"user_id": {"$in": object_id_variants(user_id)}}
        ).to_list(length=1000)

        return [follow["artist_slug"] for follow in follows]

    @staticmethod
    async def get_feed_activities(
        user_id: str,
        skip: int = 0,
        limit: int = 20,
        category: str = "all",
    ) -> list[dict]:
        """Return the unified feed timeline for a user.

        The timeline is built from the `activities` collection and scoped to
        what is relevant to the user: their own actions, actions from the
        users they follow, and actions inside the artist communities they
        follow. `category` narrows the very same timeline, it never switches
        to a different dataset.

        `following` is that timeline with the reader's own actions dropped,
        which leaves exactly what they follow: the people they follow, and
        the artist communities they follow. It is a scope over the same
        activities rather than a kind of them, so no activity type is added
        for it - attendance from a followed friend and a review under a
        followed artist's show arrive here on their own.
        """
        db = get_database()

        # An activity stores its `user_id` as a string, but the caller usually
        # holds an `ObjectId` because it read the viewer from the users
        # collection. `object_id_variants` only produces both storage forms
        # when it is given a string, so the id is normalised here.
        #
        # Without this the viewer's own actions never match their own feed: the
        # timeline silently fell back to the followed-users and
        # followed-artists clauses, which is how a filter with no reachable
        # content could look healthy.
        viewer = str(user_id)

        skip = max(0, min(skip, 10_000))
        limit = max(1, min(limit, 100))

        activity_types = FEED_CATEGORIES.get(category)

        if activity_types is None:

            raise ValueError(f"Unknown feed category: {category}")

        followed_user_ids = await ActivityService._get_followed_user_ids(
            db, viewer
        )
        followed_artist_slugs = (
            await ActivityService._get_followed_artist_slugs(db, viewer)
        )

        # The reader's own actions are the first clause of the `all` timeline
        # and the deliberate omission of `following`: what they did is not
        # something they chose to follow.
        visibility: list[dict] = []

        if category != "following":
            visibility.append(
                {"user_id": {"$in": object_id_variants(viewer)}}
            )

        if followed_user_ids:
            visibility.append(
                {
                    "user_id": {
                        "$in": [
                            value
                            for followed_id in followed_user_ids
                            for value in object_id_variants(followed_id)
                        ]
                    }
                }
            )

        if followed_artist_slugs:
            visibility.append(
                {"metadata.artist_slug": {"$in": followed_artist_slugs}}
            )

        if not visibility:
            # Follows nobody and no artist, so this scope has nothing to
            # return. Answered rather than queried: an empty `$or` is a query
            # error in Mongo, and a reader who follows nobody should get a
            # quiet empty timeline instead of a broken one.
            return []

        query: dict[str, Any] = {"$or": visibility}

        if activity_types:
            query["activity_type"] = {
                "$in": [
                    activity_type.value
                    for activity_type in activity_types
                    if activity_type not in FEED_EXCLUDED_TYPES
                ]
            }

        else:
            # Applied even to the unfiltered timeline. Excluding a type only from
            # the filter that used to contain it would leave it visible on "all",
            # which is where most people spend their time.
            query["activity_type"] = {
                "$nin": [
                    activity_type.value
                    for activity_type in FEED_EXCLUDED_TYPES
                ]
            }

        cursor = (
            db.activities.find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        activities = await cursor.to_list(length=limit)

        return await ActivityService._enrich_activities(db, activities)

    @staticmethod
    async def _load_users(db, user_ids: Iterable[str]) -> dict[str, dict]:
        wanted = {str(user_id) for user_id in user_ids}
        if not wanted:
            return {}

        oids = [to_object_id(user_id) for user_id in wanted]
        conditions = [{"_id": user_id} for user_id in wanted]
        conditions += [{"_id": oid} for oid in oids if oid is not None]

        cursor = db.users.find({"$or": conditions})
        users = await cursor.to_list(length=len(wanted))

        return {
            str(user["_id"]): {
                "id": str(user["_id"]),
                "username": user.get("username"),
                "avatar_url": user.get("avatar_url"),
                "full_name": user.get("full_name"),
            }
            for user in users
        }

    @staticmethod
    async def _load_followed_users(db, user_ids: Iterable[str]) -> dict[str, dict]:
        """Load the public handle of every user a follow activity points at.

        Actors are loaded by `_load_users`, which is for the signed-in reader
        and keeps their full profile. A follow target is only ever a name and
        a link, so it gets its own projection: nothing private leaves here.
        """
        wanted = {str(user_id) for user_id in user_ids if user_id}
        if not wanted:
            return {}

        oids = [to_object_id(user_id) for user_id in wanted]
        conditions = [{"_id": user_id} for user_id in wanted]
        conditions += [{"_id": oid} for oid in oids if oid is not None]

        cursor = db.users.find(
            {"$or": conditions},
            {"username": 1, "full_name": 1, "avatar_url": 1},
        )
        users = await cursor.to_list(length=len(wanted))

        return {
            str(user["_id"]): {
                "id": str(user["_id"]),
                "username": user.get("username"),
                "full_name": user.get("full_name"),
                "avatar_url": user.get("avatar_url"),
            }
            for user in users
        }

    @staticmethod
    async def _load_artists(db, slugs: Iterable[str]) -> dict[str, dict]:
        wanted = {slug for slug in slugs if slug}
        if not wanted:
            return {}

        cursor = db.artists.find({"slug": {"$in": sorted(wanted)}})
        artists = await cursor.to_list(length=len(wanted))

        return {
            artist["slug"]: {
                "slug": artist["slug"],
                "name": artist.get("name") or artist["slug"],
            }
            for artist in artists
        }

    @staticmethod
    async def _load_documents_by_id(db, collection: str, ids: Iterable[str]):
        wanted = {str(identifier) for identifier in ids if identifier}
        if not wanted:
            return {}

        conditions: list[dict] = [{"_id": identifier} for identifier in wanted]
        oids = [to_object_id(identifier) for identifier in wanted]
        conditions += [{"_id": oid} for oid in oids if oid is not None]

        cursor = db[collection].find({"$or": conditions})
        documents = await cursor.to_list(length=len(wanted))

        return {str(document["_id"]): document for document in documents}

    @staticmethod
    async def _load_events(db, event_ids: Iterable[str]) -> dict[str, dict]:
        """Load the event data needed by review/attendance activities in one query."""
        wanted = {str(event_id) for event_id in event_ids if event_id}
        if not wanted:
            return {}

        conditions: list[dict] = [{"_id": event_id} for event_id in wanted]
        oids = [to_object_id(event_id) for event_id in wanted]
        conditions += [{"_id": oid} for oid in oids if oid is not None]

        cursor = db.events.find({"$or": conditions})
        documents = await cursor.to_list(length=len(wanted))

        return {
            str(document["_id"]): {
                "title": document.get("title"),
                "artist_slug": document.get("artist_slug"),
                "artist_slugs": document.get("artist_slugs") or [],
                "starts_at": document.get("starts_at"),
                "venue_slug": document.get("venue_slug"),
            }
            for document in documents
        }

    @staticmethod
    async def _enrich_activities(db, activities: list[dict]) -> list[dict]:
        """Attach actor and target data to activities using batched queries.

        Every lookup is a single query per collection, so the number of
        database round trips does not grow with the page size.
        """
        if not activities:
            return []

        users = await ActivityService._load_users(
            db,
            [activity.get("user_id") for activity in activities],
        )

        target_ids_by_collection: dict[str, set[str]] = {}
        for activity in activities:
            collection = ACTIVITY_TARGET_COLLECTIONS.get(
                str(activity.get("activity_type"))
            )
            target_id = activity.get("target_id")
            if collection and target_id:
                target_ids_by_collection.setdefault(
                    collection, set()
                ).add(str(target_id))

        targets: dict[tuple[str, str], dict] = {}
        for collection, ids in target_ids_by_collection.items():
            documents = await ActivityService._load_documents_by_id(
                db, collection, ids
            )
            for identifier, document in documents.items():
                targets[(collection, identifier)] = document

        # A follow target is a person, resolved with one more batched query so
        # the row can link to that person's public profile.
        followed_users = await ActivityService._load_followed_users(
            db,
            [
                activity.get("target_id")
                for activity in activities
                if str(activity.get("activity_type"))
                == ActivityType.FOLLOW.value
            ],
        )

        # One query for every event referenced by a review/attendance item.
        event_ids = {
            str(targets[("show_logs", str(activity.get("target_id")))].get("event_id"))
            for activity in activities
            if ("show_logs", str(activity.get("target_id"))) in targets
        }
        events = await ActivityService._load_events(db, event_ids)

        artist_slugs: set[str] = set()
        for activity in activities:
            metadata = activity.get("metadata") or {}
            if metadata.get("artist_slug"):
                artist_slugs.add(metadata["artist_slug"])

            collection = ACTIVITY_TARGET_COLLECTIONS.get(
                str(activity.get("activity_type"))
            )
            document = targets.get((collection or "", str(activity.get("target_id"))))
            if document and document.get("artist_slug"):
                artist_slugs.add(document["artist_slug"])

        artists = await ActivityService._load_artists(db, artist_slugs)

        enriched: list[dict] = []
        for activity in activities:
            activity_type = str(activity.get("activity_type"))
            collection = ACTIVITY_TARGET_COLLECTIONS.get(activity_type)
            document = targets.get(
                (collection or "", str(activity.get("target_id")))
            )
            metadata = activity.get("metadata") or {}

            actor = users.get(str(activity.get("user_id")))

            artist_slug = metadata.get("artist_slug") or (
                document.get("artist_slug") if document else None
            )
            artist = artists.get(artist_slug) if artist_slug else None

            item = {
                "id": str(activity["_id"]),
                "activity_type": activity_type,
                "user": actor or {
                    "id": str(activity.get("user_id")),
                    "username": None,
                    "avatar_url": None,
                },
                "created_at": activity.get("created_at"),
                "artist": artist,
                "content": None,
                "target": None,
            }

            if activity_type == ActivityType.CREATE_COMMUNITY_POST.value and document:
                item["content"] = document.get("content")
                item["target"] = {
                    "kind": "community_post",
                    "id": str(document["_id"]),
                    "artist_slug": document.get("artist_slug"),
                    "likes_count": document.get("likes_count", 0),
                    "comments_count": document.get("comments_count", 0),
                }

            elif activity_type == ActivityType.COMMENT_POST.value and document:
                item["content"] = document.get("content")
                item["target"] = {
                    "kind": "comment",
                    "id": str(document["_id"]),
                    "post_id": str(document.get("post_id")),
                    "artist_slug": document.get("artist_slug"),
                }

            elif activity_type == ActivityType.LIKE_POST.value and document:
                item["content"] = document.get("content")
                item["target"] = {
                    "kind": "community_post",
                    "id": str(document["_id"]),
                    "artist_slug": document.get("artist_slug"),
                    "likes_count": document.get("likes_count", 0),
                    "comments_count": document.get("comments_count", 0),
                }

            elif activity_type in (
                ActivityType.CREATE_REVIEW.value,
                ActivityType.ATTEND_EVENT.value,
            ) and document:
                event = events.get(str(document.get("event_id")), {})
                item["content"] = document.get("review")
                item["rating"] = document.get("rating")
                item["attendance_status"] = document.get("status")
                item["target"] = {
                    "kind": "event",
                    "id": str(document.get("event_id")),
                    "artist_slug": event.get("artist_slug"),
                    "artist_slugs": event.get("artist_slugs"),
                    "title": event.get("title"),
                    "starts_at": event.get("starts_at"),
                    "venue_slug": event.get("venue_slug"),
                }

            elif activity_type == ActivityType.FOLLOW.value:
                followed = followed_users.get(str(activity.get("target_id")))
                item["target"] = {
                    "kind": "profile",
                    "id": str(activity.get("target_id")),
                    "username": followed.get("username") if followed else None,
                }

            enriched.append(item)

        return enriched

    # =====================================================
    # NOTIFICATIONS
    # =====================================================

    @staticmethod
    async def create_notification(
        recipient_id: str,
        actor_id: str,
        notification_type: NotificationType,
        *,
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> Optional[dict]:
        """Create a notification for `recipient_id`.

        Self-notifications are never created: acting on your own content is
        not news to you. Returns the stored document, or None when the
        notification was skipped.
        """
        if str(recipient_id) == str(actor_id):
            return None

        db = get_database()

        document = {
            "recipient_id": str(recipient_id),
            "actor_id": str(actor_id),
            "type": NotificationType(notification_type).value,
            "related_entity_type": related_entity_type,
            "related_entity_id": (
                str(related_entity_id) if related_entity_id else None
            ),
            "context": context or {},
            "read": False,
            "created_at": datetime.now(UTC),
        }

        result = await db.notifications.insert_one(document)
        document["_id"] = str(result.inserted_id)

        return document

    @staticmethod
    async def notify(
        recipient_id: str,
        actor_id: str,
        notification_type: NotificationType,
        *,
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> None:
        """Best-effort notification trigger used by action routes.

        Self-notifications are dropped by `create_notification`.
        """
        try:
            await ActivityService.create_notification(
                recipient_id,
                actor_id,
                notification_type,
                related_entity_type=related_entity_type,
                related_entity_id=related_entity_id,
                context=context,
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to create notification %s", notification_type)

    @staticmethod
    async def get_notifications(
        user_id: str,
        skip: int = 0,
        limit: int = 30,
    ) -> dict:
        """Return the caller's notifications, newest first.

        Scoped by `recipient_id` so a user can never read another user's
        notifications. The actor is resolved for the whole page at once.
        """
        db = get_database()

        skip = max(0, min(skip, 10_000))
        limit = max(1, min(limit, 100))

        cursor = (
            db.notifications.find({"recipient_id": str(user_id)})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        documents = await cursor.to_list(length=limit)

        total = await db.notifications.count_documents(
            {"recipient_id": str(user_id)}
        )
        unread_count = await db.notifications.count_documents(
            {"recipient_id": str(user_id), "read": False}
        )

        actors = await ActivityService._load_users(
            db,
            [document.get("actor_id") for document in documents],
        )

        artist_slugs = {
            (document.get("context") or {}).get("artist_slug")
            for document in documents
        }
        artists = await ActivityService._load_artists(
            db, {slug for slug in artist_slugs if slug}
        )

        post_ids = {
            str((document.get("context") or {}).get("post_id"))
            for document in documents
            if (document.get("context") or {}).get("post_id")
        }
        posts = await ActivityService._load_documents_by_id(
            db, "community_posts", post_ids
        )

        # `NotificationResponse` (not the bare DB model) because the actor and
        # the navigation target are part of the payload the UI needs. Building
        # the narrow model here would silently drop them.
        notifications: list[NotificationResponse] = []
        for document in documents:
            context = document.get("context") or {}

            target: Optional[dict] = None
            post_id = context.get("post_id")
            post = posts.get(str(post_id)) if post_id else None

            if document.get("related_entity_type") == "event" and (
                document.get("related_entity_id")
            ):
                # A prompt about a show links straight to the show, where the
                # attendance and review controls already are. No separate
                # destination is invented for it.
                target = {
                    "kind": "event",
                    "id": str(document["related_entity_id"]),
                    "name": context.get("event_title"),
                    "artist_slug": context.get("artist_slug"),
                    "starts_at": context.get("starts_at"),
                    "excerpt": None,
                }
            elif post:
                target = {
                    "kind": "community_post",
                    "id": str(post["_id"]),
                    "artist_slug": post.get("artist_slug"),
                    "excerpt": (post.get("content") or "")[:160],
                }
            elif context.get("comment_id"):
                target = {
                    "kind": "comment",
                    "id": str(context["comment_id"]),
                    "artist_slug": context.get("artist_slug"),
                    "excerpt": (context.get("excerpt") or "")[:160],
                }
            elif context.get("artist_slug"):
                artist = artists.get(context["artist_slug"], {})
                target = {
                    "kind": "artist",
                    "id": context["artist_slug"],
                    "slug": context["artist_slug"],
                    "name": artist.get("name") or context["artist_slug"],
                }

            actor = actors.get(str(document.get("actor_id"))) or {
                "id": str(document.get("actor_id")),
                "username": None,
                "avatar_url": None,
            }

            enriched = {
                "_id": str(document["_id"]),
                "recipient_id": document["recipient_id"],
                "actor_id": document["actor_id"],
                "type": document["type"],
                "related_entity_type": document.get("related_entity_type"),
                "related_entity_id": document.get("related_entity_id"),
                "context": {
                    **context,
                    "artist_name": (
                        artists.get(
                            context.get("artist_slug"), {}
                        ).get("name")
                        if context.get("artist_slug")
                        else None
                    ),
                },
                "read": bool(document.get("read", False)),
                "created_at": document.get("created_at"),
                "actor": actor,
                "target": target,
            }

            notifications.append(NotificationResponse(**enriched))

        return {
            "notifications": notifications,
            "unread_count": unread_count,
            "total": total,
        }

    @staticmethod
    async def get_unread_count(user_id: str) -> int:
        db = get_database()
        return await db.notifications.count_documents(
            {"recipient_id": str(user_id), "read": False}
        )

    @staticmethod
    async def mark_as_read(
        notification_id: str,
        user_id: str,
    ) -> bool:
        """Mark one notification read. Recipient scoped."""
        db = get_database()

        oid = to_object_id(notification_id)
        if oid is None:
            return False

        result = await db.notifications.update_one(
            {
                "_id": oid,
                "recipient_id": str(user_id),
            },
            {"$set": {"read": True}},
        )

        return result.matched_count > 0

    @staticmethod
    async def mark_all_as_read(user_id: str) -> int:
        """Mark every notification read. Recipient scoped."""
        db = get_database()

        result = await db.notifications.update_many(
            {"recipient_id": str(user_id), "read": False},
            {"$set": {"read": True}},
        )

        return result.modified_count
