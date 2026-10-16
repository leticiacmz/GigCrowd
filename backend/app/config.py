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
    # Background scheduler
    # =====================================================
    # One clock, for two passes: refreshing artist event catalogues through
    # the same extraction pipeline a manual sync uses, and the event lifecycle
    # prompts. Nothing here revisits an event because it was written short of
    # a field - an extraction gap is reported where it is found, and the next
    # catalog refresh re-reads the source through this same pipeline.
    #
    # It is OFF by default on purpose: turning it on means this process starts
    # making outbound requests to Songkick on its own, and that must never
    # happen merely because someone ran the API locally. Production is
    # expected to set SCHEDULER_ENABLED=true explicitly.

    SCHEDULER_ENABLED: bool = False

    # How long to wait between runs.
    SCHEDULER_INTERVAL_MINUTES: int = 360

    # =====================================================
    # FIRST-PASS COMPLETENESS
    # =====================================================
    # An extraction reads the artist page, the calendar, the gigography and the
    # search results, then joins everything those pages state about an event
    # under its id. What that leaves out - chiefly a festival's lineup, and a
    # listing Songkick published with no date on it - is stated only on the
    # event's own page, so one run reads those pages itself instead of owing
    # them to a later pass.
    #
    # This bounds how many of those pages one scrape may read. It is a bound,
    # not a budget: an event that arrived complete costs nothing, and events
    # past the bound are reported as extraction gaps in the import summary
    # rather than handed to anything else. Set it to 0 to read only the pages
    # the scrape pays for anyway.

    SONGKICK_EVENT_PAGE_READS_PER_SCRAPE: int = 25

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

    # =====================================================
    # LINEUP ENRICHMENT
    # =====================================================
    # The one deferred pass this project deliberately has. An imported
    # festival event is written, reported and visible with whatever the run
    # obtained; when its listing stated only part of the bill, the event's
    # own page is read afterwards as background work, and the edition
    # carries the state of that work (`lineup_state`) so a page can show
    # "being updated" instead of pretending one headliner is the lineup.
    #
    # On by default, and note what governs when it may work: it only runs
    # for events an import just wrote, or when the festival page's retry is
    # asked for. Starting the API on its own begins no reads - there is no
    # clock and no scheduler pass behind it - so the local rule ("a page
    # view and a boot never go to Songkick") holds unchanged.

    LINEUP_ENRICHMENT_ENABLED: bool = True

    # How long one enrichment claim is fresh for. A worker that died
    # mid-read leaves an `active` state behind; after this long the claim
    # is taken over. Longer than the longest single page read by a wide
    # margin, because a takeover mid-run is what the bound exists to
    # prevent.
    LINEUP_ENRICHMENT_LEASE_SECONDS: int = 600

    # How many attempts one edition gets before it stops retrying itself.
    # The retry button on the festival page resets the counter, so a person
    # always has the last word over an automatic budget.
    LINEUP_ENRICHMENT_MAX_ATTEMPTS: int = 3

    # How many new artist stubs one enrichment pass may create, mirroring
    # the import's own bound. A bill past the bound stores completely and
    # reports `partial` - performers are held, the tail's artist pages are
    # simply not created yet, and the next pass continues.
    LINEUP_ENRICHMENT_MAX_NEW_ARTISTS: int = 100

    # How many page reads one process keeps in flight at once. The claims
    # bound this across processes; this bounds it within one.
    LINEUP_ENRICHMENT_MAX_CONCURRENT: int = 2

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

    # How long one artist's sync lease stays fresh while a worker holds it.
    # Longer than the longest scrape this project expects - a full sync
    # takes minutes - so a slow but alive worker is never taken over for
    # being slow, and short enough that a worker that died mid-scrape does
    # not lock the artist away for the rest of the day.
    ARTIST_SYNC_LOCK_TTL_SECONDS: int = 900

    CORS_ORIGINS: List[str]


settings = Settings()