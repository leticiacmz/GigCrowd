from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List


class Settings(BaseSettings):
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True
    )
    
    APP_NAME: str
    APP_VERSION: str
    DEBUG: bool

    MONGODB_URL: str
    DATABASE_NAME: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int

    MAX_IMAGE_SIZE_MB: int
    UPLOAD_DIR: str

    CLOUDINARY_CLOUD_NAME: Optional[str]
    CLOUDINARY_API_KEY: Optional[str]
    CLOUDINARY_API_SECRET: Optional[str]

    BANDSINTOWN_APP_ID: str
    BANDSINTOWN_BASE_URL: str
    
    SPOTIFY_CLIENT_ID: str
    SPOTIFY_CLIENT_SECRET: str
    SPOTIFY_REDIRECT_URI: str
    SPOTIFY_API_URL: str 
    SPOTIFY_AUTH_URL: str 
    
    # Songkick configuration
    SONGKICK_BASE_URL: str = "https://www.songkick.com"
    PLAYWRIGHT_HEADLESS: bool = True
    PLAYWRIGHT_TIMEOUT: int = 60000
    SONGKICK_REQUIRE_NAVIGATION: bool = True

    # =====================================================
    # Scheduled event enrichment
    # =====================================================
    # The scheduler keeps incomplete Songkick events moving without anyone
    # remembering to run a script. It is OFF by default on purpose: turning it
    # on means this process starts making outbound requests to Songkick on its
    # own, and that must never happen merely because someone ran the API
    # locally. Production is expected to set ENRICHMENT_SCHEDULER_ENABLED=true
    # explicitly.

    ENRICHMENT_SCHEDULER_ENABLED: bool = False

    # How long to wait between runs.
    ENRICHMENT_SCHEDULER_INTERVAL_MINUTES: int = 360

    # How many events one run may attempt. A run is bounded so a scheduler can
    # never spend an unbounded amount of time inside someone else's servers.
    ENRICHMENT_SCHEDULER_BATCH_SIZE: int = 25

    # Seconds to wait between source requests inside a run. This is politeness
    # toward Songkick, not a tuning knob.
    ENRICHMENT_SCHEDULER_REQUEST_DELAY_SECONDS: float = 1.5

    # Which missing fields to chase, using the enrichment service's own
    # vocabulary: dates, lineup, location or all.
    ENRICHMENT_SCHEDULER_FIELDS: str = "dates"

    # Whether to also revisit events that already have a date. Needed for
    # lineup and location work, and pointless for dates.
    ENRICHMENT_SCHEDULER_INCLUDE_DATED: bool = False

    # Whether to run once immediately on startup instead of waiting a full
    # interval. Off by default so starting the API never triggers a burst of
    # outbound requests.
    ENRICHMENT_SCHEDULER_RUN_ON_STARTUP: bool = False

    # =====================================================
    # ENRICHMENT DURING IMPORT
    # =====================================================
    # A Songkick gigography is a listing, and a listing routinely names an event
    # without stating its date even though the event's own page carries one. An
    # import that wrote that row and stopped has imported an event nobody can
    # place in time, and the only remedy was a human remembering to run a
    # backfill afterwards.
    #
    # So an import reads the concrete source for anything it has just written
    # that is still incomplete. This is ON by default, because it is the normal
    # path rather than an extra: the alternative is imported data that is wrong
    # until someone notices. Turning it off only moves the work to the
    # scheduler, and leaves the record incomplete in the meantime.

    ENRICH_ON_IMPORT_ENABLED: bool = True

    # Which missing fields to chase during an import, using the same vocabulary
    # as the scheduler. Dates by default, because a date is the one thing that
    # makes an event usable and the one a listing most often leaves out.
    ENRICH_ON_IMPORT_FIELDS: str = "dates"

    # How many incomplete events one import may read the source of.
    #
    # It is a bound, not a budget: it has to be larger than the backlog one
    # import can actually create, or the surplus is quietly handed to the
    # scheduler, which drains 25 an hour. On 2026-10-07 a full-catalogue
    # import left 585 incomplete festival listings while this bound was 60,
    # and 108 of them were still undated fourteen hours later.
    #
    # The bound still exists so a pathological run cannot spend forever
    # inside Songkick, and the import stops early on its own when the source
    # stops answering: five consecutive failures defer the rest.
    ENRICH_ON_IMPORT_MAX_EVENTS: int = 1000

    # Seconds between source requests during an import. Politeness toward
    # Songkick, same as the scheduler's delay.
    ENRICH_ON_IMPORT_DELAY_SECONDS: float = 1.5

    # =====================================================
    # LINEUP ARTISTS
    # =====================================================
    # A festival announces far more artists than the catalogue has imported, and
    # every one of them used to render as a name with a note saying it was not
    # here yet. Turning an announced performer into an artist is what makes a
    # lineup pressable.
    #
    # On by default, and note what it does NOT do: it creates the artist record
    # and stops. It writes no `last_synced_at` and starts no gigography fetch,
    # because artist creation and artist import are different jobs. Folding a
    # fetch into this would rebuild the old bug where looking at a page changed
    # the database.

    LINEUP_ARTIST_IMPORT_ENABLED: bool = True

    # How many distinct performers one import may turn into artists. Bounded so
    # a single festival with a very large bill cannot turn one sync into a very
    # long run of writes.
    LINEUP_ARTIST_IMPORT_MAX_ARTISTS: int = 100

    # ============================================================
    # EVENT LIFECYCLE
    #
    # Asks people about shows that have already finished: whether they went, or
    # what they thought of it.
    #
    # It shares the scheduler above rather than having its own clock, and it is
    # off unless configuration turns it on. A lifecycle pass sends notifications
    # to real people, so on a development database it must never begin working
    # through a backlog unasked.
    # ============================================================

    EVENT_LIFECYCLE_SCHEDULER_ENABLED: bool = False

    # How many show logs one pass may consider. Bounded so a pass cannot spend
    # unbounded time, and so a run that falls behind catches up over several
    # passes rather than in one enormous one.
    EVENT_LIFECYCLE_SCHEDULER_BATCH_SIZE: int = 50

    # How far back a pass looks, measured from when an event finished rather
    # than from when its show log was written. Without a bound, the first pass
    # on an established database would ask about every historical show at once.
    EVENT_LIFECYCLE_SCHEDULER_LOOKBACK_HOURS: int = 48

    # ============================================================
    # ARTIST SYNCHRONIZATION
    #
    # Importing an artist's gigography from Songkick used to happen as a side
    # effect of `GET /artists/{slug}`. It is a scheduled job now, on the same
    # clock and the same switch as the passes above.
    #
    # Off by default, for the same reason they are: a pass visits Songkick's
    # servers on this process's own initiative, and running the API locally must
    # never start that without being asked.
    # ============================================================

    ARTIST_SYNC_SCHEDULER_ENABLED: bool = False

    # How long to wait between passes. Generous by design: a full artist sync is
    # one gigography page, and doing the whole catalogue daily is plenty.
    ARTIST_SYNC_SCHEDULER_INTERVAL_MINUTES: int = 360

    # How many artists one pass may visit. Bounded so a tick can never become a
    # full-catalog scrape, and so a pass that falls behind catches up over several
    # runs rather than in one enormous one. The selection is ordered by how long
    # each artist has waited, so a batch too small still makes progress.
    ARTIST_SYNC_SCHEDULER_BATCH_SIZE: int = 10

    # Seconds between artists inside one pass. Politeness toward Songkick, not a
    # tuning knob.
    ARTIST_SYNC_SCHEDULER_REQUEST_DELAY_SECONDS: float = 1.5

    # Whether to run once immediately on startup instead of waiting a full
    # interval. Off by default so booting the API never triggers a burst of
    # outbound requests.
    ARTIST_SYNC_SCHEDULER_RUN_ON_STARTUP: bool = False

    # How long an artist's imported data is considered fresh. An artist synced
    # more recently than this is skipped, which is the same rule the request path
    # used to apply - it now only applies here, and to the scheduler's selection.
    #
    # Read by SynchronizationService as well as by the job, so there is one
    # definition of "stale" rather than one per caller.
    ARTIST_SYNC_TTL_HOURS: int = 24

    CORS_ORIGINS: List[str]


settings = Settings()