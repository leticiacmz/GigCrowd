from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime

from app.domain.lineup import LineupEntry, dedupe_lineup


class Event(BaseModel):

    id: Optional[str] = None

    external_ids: dict[str, str] = Field(
        default_factory=dict,
    )

    # ============================================================
    # ARTISTS
    # ============================================================

    artist_slugs: List[str] = Field(
        default_factory=list,
        description=(
            "List of artist slugs for this event "
            "(supports festivals)"
        ),
    )

    # Backward compatibility
    artist_slug: str = Field(
        default="",
        description=(
            "Primary artist slug "
            "(transitional field for backward compatibility)"
        ),
    )

    # ============================================================
    # VENUE
    # ============================================================

    venue_slug: str

    # ============================================================
    # EVENT
    # ============================================================

    title: str

    starts_at: Optional[datetime] = None

    ends_at: Optional[datetime] = Field(
        default=None,
        description="End date for multi-day events and festivals",
    )

    event_type: str = Field(
        default="Concert",
        description=(
            "Event type such as Concert, FestivalInstance "
            "or Livestream"
        ),
    )

    # ============================================================
    # FESTIVAL
    # ============================================================

    festival: Optional[dict] = Field(
        default=None,
        description=(
            "Festival metadata such as series, edition, "
            "name and tracking count"
        ),
    )

    # ============================================================
    # LINEUP
    # ============================================================

    lineup: List[LineupEntry] = Field(
        default_factory=list,
        description=(
            "Performers announced for this event, in the "
            "order the source lists them. Empty when the "
            "source names no one, which is different from "
            "a lineup that could not be read."
        ),
    )

    @field_validator("lineup", mode="after")
    @classmethod
    def _one_row_per_performer(cls, value: list) -> list:
        """A performer is on a bill once.

        Ingest already drops a repeated act, but a lineup can also arrive from
        an import, a fixture or a partial patch, and the same act listed twice
        is still one act. Enforcing it on the domain value rather than on one
        read path means no response can show an artist's name twice, and a count
        of how many artists performed cannot disagree with the number of rows.

        The stored document is left alone; this is about what a reader is shown.
        """

        return dedupe_lineup(value)

    # ============================================================
    # DATE PROVENANCE
    # ============================================================

    date_status: Optional[str] = Field(
        default=None,
        description=(
            "How the dates on this event were resolved: "
            "'source' when they came from the provider, "
            "'unavailable' when the provider exposed none, "
            "'parser_failed' when a date was present but "
            "could not be read. Used to decide which events "
            "are still worth a second visit."
        ),
    )

    # ============================================================
    # LOCATION
    # ============================================================

    location: Optional[dict] = Field(
        default=None,
        description=(
            "Event location metadata such as city, country "
            "and geographic coordinates"
        ),
    )

    # ============================================================
    # SOURCE
    # ============================================================

    source: Optional[dict] = Field(
        default=None,
        description=(
            "Provider/source metadata for the event"
        ),
    )

    # ============================================================
    # TICKETS / STATUS
    # ============================================================

    sold_out: bool = False

    free: bool = False

    ticket_url: Optional[str] = None

    # ============================================================
    # ATTENDANCE
    # ============================================================

    going_count: int = 0

    maybe_count: int = 0

    went_count: int = 0