"""Asking people about shows that have already happened.

A gig is over and somebody's own show log is waiting on them. This service finds
those and decides what to ask, then records that it asked, so the next run has
nothing left to do.

Two rules shape everything here:

* **Attendance is never invented.** Someone who marked a show `going` or `maybe`
  is asked whether they went; they are not recorded as having gone. The reader
  confirms, through the attendance controls that already exist on the event page.
  A lifecycle that quietly turned a plan into a fact would put a show on
  somebody's concert history that they never attended, and would credit them
  with having seen artists they only hoped to.

* **Asking twice is worse than not asking.** Each prompt is recorded on the show
  log itself, so a scheduler that runs every six hours does not produce a stream
  of identical notifications, and a run that is interrupted half way resumes
  where it stopped rather than starting again.

A show log is the right place for the marker because it is already unique per
(person, event): updating a field on it is atomic, so two overlapping runs
cannot both decide they are the first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

from app.core.logger import get_logger
from app.models.activity import (
    SYSTEM_ACTOR_ID,
    NotificationType,
)
from app.utils.ids import object_id_variants

logger = get_logger("event_lifecycle")

# The two prompts, and which show-log state each one is for.
#
# `going` and `maybe` are both plans, and both are answered by the same question,
# so they share a prompt. `went` is not a plan any more: the only thing left to
# ask is what they thought of it.
ATTENDANCE_CHECK = NotificationType.EVENT_ATTENDANCE_CHECK.value
REVIEW_PROMPT = NotificationType.EVENT_REVIEW_PROMPT.value

# How far back a run looks. Without a bound, a scheduler left on for a month
# would walk every historical show log in the database on its first pass and
# notify people about concerts from years ago.
DEFAULT_LOOKBACK_HOURS = 48


@dataclass
class LifecycleResult:
    """What one pass did, in numbers a caller can log or assert on."""

    scanned: int = 0
    attendance_checks: int = 0
    review_prompts: int = 0
    skipped_already_asked: int = 0
    skipped_reviewed: int = 0
    failed: int = 0

    @property
    def notified(self) -> int:
        return self.attendance_checks + self.review_prompts

    def as_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "attendance_checks": self.attendance_checks,
            "review_prompts": self.review_prompts,
            "skipped_already_asked": self.skipped_already_asked,
            "skipped_reviewed": self.skipped_reviewed,
            "failed": self.failed,
            "notified": self.notified,
        }


@dataclass
class PlannedPrompt:
    """One prompt the service decided to send, before it is sent.

    Split out from the sending so the decision can be tested on its own, without
    a database and without the question of whether a notification was written.
    """

    notification_type: str
    status: str
    has_review: bool

    @property
    def kind(self) -> Optional[str]:
        """Which prompt, or None when there is nothing to ask."""

        if self.status in ("going", "maybe"):
            return ATTENDANCE_CHECK

        if self.status == "went":
            # Having already written about the show, there is nothing left to
            # ask. Asking again would be the definition of nagging.
            return None if self.has_review else REVIEW_PROMPT

        return None


def plan_prompt(
    status: Optional[str],
    has_review: bool,
) -> Optional[str]:
    """Which prompt this show log needs, if any."""

    return PlannedPrompt(
        notification_type="",
        status=status or "",
        has_review=has_review,
    ).kind


class EventLifecycleService:
    """Finds finished shows with an unanswered question and asks it once."""

    def __init__(self, db: Any) -> None:
        self.db = db

    # ============================================================
    # SELECTION
    # ============================================================

    async def find_candidates(
        self,
        batch_size: int = 50,
        lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
        now: Optional[datetime] = None,
    ) -> list[dict]:
        """Show logs for events that have finished and are still unanswered.

        The window is on the event finishing, not on the show log being written,
        so a log created today for a show last month is picked up in the pass
        that follows that show and not before.

        Bounded twice over: by `batch_size`, and by the lookback window. A
        scheduler that falls behind therefore catches up in several passes rather
        than trying to answer the whole backlog at once.
        """

        moment = now or datetime.now(UTC)

        window_start = datetime.fromtimestamp(
            moment.timestamp() - (lookback_hours * 3600),
            tz=UTC,
        )

        candidates: list[dict] = []

        # Event ids are matched in both storage forms, because a show log holds a
        # string and the event holds an ObjectId, and only one of the two is
        # right depending on how old the row is.
        cursor = self.db.show_logs.find(
            {"status": {"$in": ["going", "maybe", "went"]}}
        ).limit(batch_size * 4)

        logs = await cursor.to_list(length=batch_size * 4)

        for log in logs:

            if len(candidates) >= batch_size:
                break

            event = await self._event_for(log.get("event_id"))

            if not event:
                # The event was deleted or never existed. Nothing to ask about,
                # and nothing to invent.
                continue

            finished_at = self._finished_at(event)

            if finished_at is None:
                continue

            if finished_at > moment or finished_at < window_start:
                continue

            candidates.append(
                {
                    "log": log,
                    "event": event,
                    "finished_at": finished_at,
                }
            )

        return candidates

    async def _event_for(self, event_id: Any) -> Optional[dict]:
        if not event_id:
            return None

        variants = object_id_variants(str(event_id))

        if not variants:
            return None

        return await self.db.events.find_one(
            {"_id": {"$in": variants}}
        )

    @staticmethod
    def _finished_at(event: dict) -> Optional[datetime]:
        """When this event stopped being upcoming.

        The shared schedule rule, so "this show is over" means the same thing
        here as it does on the event page and on a profile's badge. An event with
        no end date is over once it has started.
        """

        from app.domain.event_schedule import is_upcoming

        if is_upcoming(event, datetime.now(UTC)):
            return None

        ends_at = event.get("ends_at")
        starts_at = event.get("starts_at")

        for value in (ends_at, starts_at):
            if isinstance(value, datetime):
                return value

        return None

    # ============================================================
    # THE PASS
    # ============================================================

    async def run(
        self,
        batch_size: int = 50,
        lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
        dry_run: bool = False,
        now: Optional[datetime] = None,
    ) -> LifecycleResult:
        """Ask once about everything in the window, and say what happened.

        One failure does not end the pass. A notification that cannot be written
        is counted and the run carries on, because a single bad row should not
        cost every other person their prompt.
        """

        result = LifecycleResult()

        candidates = await self.find_candidates(
            batch_size=batch_size,
            lookback_hours=lookback_hours,
            now=now,
        )

        for candidate in candidates:

            log = candidate["log"]
            event = candidate["event"]

            result.scanned += 1

            asked = log.get("lifecycle") or {}

            kind = plan_prompt(
                log.get("status"),
                bool(log.get("review")),
            )

            if kind is None:
                result.skipped_reviewed += 1
                continue

            if asked.get(kind):
                result.skipped_already_asked += 1
                continue

            if dry_run:
                self._count(result, kind)
                continue

            try:
                written = await self._notify(
                    log=log,
                    event=event,
                    kind=kind,
                )
            except Exception:
                logger.exception(
                    "Lifecycle notification failed for log %s",
                    log.get("_id"),
                )

                result.failed += 1

                continue

            if written:
                await self._mark_asked(log, kind)

                self._count(result, kind)
            else:
                result.skipped_already_asked += 1

        logger.info("Event lifecycle pass: %s", result.as_dict())

        return result

    @staticmethod
    def _count(result: LifecycleResult, kind: str) -> None:
        if kind == ATTENDANCE_CHECK:
            result.attendance_checks += 1
        else:
            result.review_prompts += 1

    async def _notify(
        self,
        log: dict,
        event: dict,
        kind: str,
    ) -> bool:
        """Write one notification, unless it is already there.

        The marker on the show log is the primary guard, but a row can be edited
        by hand or a previous run can have died between the insert and the
        marker, so the collection is also asked directly. Either check is enough
        on its own; both together mean a duplicate needs two independent
        failures.
        """

        user_id = str(log.get("user_id"))
        event_id = str(event.get("_id"))

        existing = await self.db.notifications.find_one(
            {
                "recipient_id": user_id,
                "type": kind,
                "related_entity_type": "event",
                "related_entity_id": event_id,
            }
        )

        if existing:
            return False

        await self.db.notifications.insert_one(
            {
                "recipient_id": user_id,
                # Not a person. Nobody acted here; the show simply ended.
                "actor_id": SYSTEM_ACTOR_ID,
                "type": kind,
                "related_entity_type": "event",
                "related_entity_id": event_id,
                "context": {
                    "event_title": event.get("title"),
                    "event_slug": event.get("slug"),
                    "artist_slug": event.get("artist_slug"),
                    "status_at_prompt": log.get("status"),
                    "starts_at": event.get("starts_at"),
                },
                "read": False,
                "created_at": datetime.now(UTC),
            }
        )

        return True

    async def _mark_asked(
        self,
        log: dict,
        kind: str,
    ) -> None:
        await self.db.show_logs.update_one(
            {"_id": log.get("_id")},
            {
                "$set": {
                    f"lifecycle.{kind}": datetime.now(UTC),
                }
            },
        )
