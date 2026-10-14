# Background jobs

There is exactly one scheduler in this project and it is `scheduler.py`. It owns
a clock and nothing else.

## The lifecycle

An imported event is not trusted to be complete just because the listing was
read. Songkick's gigography names festival dates **without dating them**, while
each of those dates has a page of its own carrying the real `startDate` and
`endDate`. Measured on a single artist: 41 of 45 festival entries arrived with
no date at all.

So the run that creates the row is also the run that finishes it:

```
artist page + calendar + gigography + search     ← paid for once
    ↓
join everything they state, by event id           ← SongkickClient
    ↓
still missing something?  ── yes ──→ read that event's own page, once, now
    ↓ no                                          ← SongkickClient._complete_missing_fields
event persisted
    ↓
what is still missing is reported                 ← SongkickEventImportService
    event id, field, source
```

There is no third step. Nothing is deferred, nothing is queued and nothing comes
back later: a gap found by extraction is a fact about the source, reported where
it was found, and the next catalog refresh re-reads the source through this same
pipeline.

| Stage | Entry point | Bounded by |
| --- | --- | --- |
| Join (no cost) | `SongkickClient._merge_event_details` | — |
| Complete | `SongkickClient._complete_missing_fields` | `SONGKICK_EVENT_PAGE_READS_PER_SCRAPE` |
| Report | `SongkickEventImportService` → `extraction_gaps()` | — |
| Refresh | `scheduler` → `run_artist_sync_once` | `ARTIST_SYNC_SCHEDULER_BATCH_SIZE` |

The import reports what it could not obtain: `events_with_extraction_gaps`,
`extraction_gaps` (by field), `events_extraction_failed`, and the request cost of
completion (`event_pages_read`, `event_pages_unread`, `event_pages_failed`).
Nothing in that report is a promise to anybody.

### Measured

Request cost of one scrape and one import, before (`HEAD`) and after, on the
same fixture pages with the same stub transport
(`measure_first_pass_requests.py`):

| Scenario | before | after |
| --- | --- | --- |
| Scrape of an already-complete catalogue | 3 requests, dated | 3 requests, dated |
| Scrape of a listing with no date on those pages | 3 requests, **undated** | 4 requests, **dated** (`event_pages_read=1`) |
| Import of 5 incomplete events | 5 source requests + 7.5s of pacing | **0 requests, 0s**, gaps reported |

The extra request in the second row is the whole change: a page that was
requested anyway by a later, unguaranteed pass is requested once, now, by the
run that creates the row. A complete event still costs nothing.

The counts in a summary are of this run. They describe the database as it now
stands, so a summary can be read against the rows rather than against a backlog:

```
[EVENT IMPORT] 🔎 Event pages read during extraction: 4 (bound 25), unreadable: 0
[EVENT IMPORT] ⚠️ Extraction gaps (absent in every page this run read): 3 event(s) {'date': 1, 'lineup': 2}
```

```
scheduler.py        when a pass runs (catalog refresh, lifecycle)
    ↓
artist_sync_job.py  which artists are stale
    ↓
SynchronizationService → EventImportService → SongkickEventImportService
    ↓
SongkickClient            the same extraction a manual sync performs
    ↓
MongoDB                   field-level merge of what was missing
```

The dependency runs one way: scheduler → job → pipeline. Neither a job nor the
service imports the scheduler, so a scheduled refresh and a manual one execute
exactly the same code.

## What may read with a write, and what may not

There is exactly one path in this project where a read causes a write:

    first open of a *pending* artist
        → take the initialization claim
        → SynchronizationService.synchronize_artist(force=True)
        → the artist's gigography is fetched and stored
        → every later read of that artist is a plain read

An artist is **pending** when its identity is established but no gigography has
ever been fetched — which is exactly the record a festival lineup leaves behind.
`sync_status` and `last_synced_at` together say so; see
`app/domain/artist_state.py`. An **initialized** artist's page is read-only on
every subsequent view, and an **errored** one is retried on a cooldown rather
than on every view.

The claim is what makes "once" true rather than merely likely: two people opening
a cold artist in the same instant is an ordinary thing for a catalogue to see, and
without a compare-and-set both would spend a full gigography scrape to produce the
same rows. The loser of the race does nothing at all.

Two consequences worth stating rather than discovering:

* **A first open is slow.** Measured against the live provider: 42s for a
  mid-sized catalogue, 111s for a large one. It is not slow because the read is
  wrong; it is doing the work the reader came for. The HTTP calls already run off
  the event loop, so the rest of the API stays responsive throughout — 252
  concurrent requests during a 111s import were served at a 0.02s median with no
  failures.
* **This job is not how the catalogue fills up.** Its selection requires positive
  evidence that a fetch already happened. "Never-synced is eligible" was how it
  used to drain thousands of announced-but-unopened artists: the batch filled with
  the same cold rows every hour and nobody who actually followed an artist ever
  got refreshed. An artist is initialized by an import or a first open, and at no
  other time.

`ArtistService` still does not hold a `synchronization_service` at all — the
dependency is *absent* from it, not merely unused, so putting a write back on a
read path means adding it on purpose in a diff that says so. The one read that may
write is stated in `app/routes/artists.py` and nowhere else.

## What one extraction completes

Selection of the extra pages is extraction's own, and it is deliberately narrow.
An event is worth one request when *every* page already read still leaves it
short of a field an event page is expected to carry:

| Missing | Worth reading? | Why |
| --- | --- | --- |
| date | yes | The listing published it; the event's page states it |
| venue | yes | Same, and only when the payload named no venue at all |
| lineup (festivals only) | yes | A bill is announced on the festival page, nowhere else |
| livestream venue | no | An event that is placeless is not missing a venue |
| description, image | no | Presentation; frequently absent at the source |

Rules, all pinned in `tests/providers/songkick/test_first_pass_completion.py`:

* an event that arrived complete costs **zero** requests;
* one request per event, however many fields it is missing;
* most incomplete first, so the bound is spent where a reader would notice;
* the result is written onto the event dict itself, because `events`,
  `upcoming` and `upcoming_festivals` all hold the same object;
* a page that does not answer changes nothing and is counted as a failure.

### What a gap is

A gap is a field that no page read this run states, judged on the event that was
just written — so the count describes stored state, not the payload's shape:

* no `starts_at` and no `ends_at`
* no venue name the source ever said (the mapper's `Unknown Venue`), unless the
  event is a livestream
* a festival with no announced lineup

`date_status = parser_failed` is **not** a gap: it is a failure. The source
states a date and this run could not read it, which needs a person looking at a
parser rather than another request.

`description` and `image_url` are deliberately not gaps. They are presentation,
they are regularly absent at the source, and counting them would make every run
look broken.

## Configuration

### The scheduler

| Variable | Default | Meaning |
| --- | --- | --- |
| `SCHEDULER_ENABLED` | `false` | Whether the scheduler runs at all |
| `SCHEDULER_INTERVAL_MINUTES` | `360` | Minutes between ticks |

### Artist synchronization (what a tick refreshes)

| Variable | Default | Meaning |
| --- | --- | --- |
| `ARTIST_SYNC_SCHEDULER_ENABLED` | `false` | Import gigographies for stale artists |
| `ARTIST_SYNC_SCHEDULER_INTERVAL_MINUTES` | `360` | Reported on the status endpoint |
| `ARTIST_SYNC_SCHEDULER_BATCH_SIZE` | `10` | Artists one pass may sync |
| `ARTIST_SYNC_SCHEDULER_REQUEST_DELAY_SECONDS` | `1.5` | Pause between artists |
| `ARTIST_SYNC_SCHEDULER_RUN_ON_STARTUP` | `false` | One refresh immediately on boot |
| `ARTIST_SYNC_TTL_HOURS` | `24` | How old a sync may be |

### First-pass completeness

| Variable | Default | Meaning |
| --- | --- | --- |
| `SONGKICK_EVENT_PAGE_READS_PER_SCRAPE` | `25` | Event pages one scrape may read to finish what no other page states |

`0` disables those reads entirely: the scrape then costs exactly the pages it
already pays for, and everything it could not state is reported as a gap. It is a
bound, not a budget — an event that arrived complete costs nothing either way.

### Event lifecycle

| Variable | Default | Meaning |
| --- | --- | --- |
| `EVENT_LIFECYCLE_SCHEDULER_ENABLED` | `false` | Prompts for shows that have finished |
| `EVENT_LIFECYCLE_SCHEDULER_BATCH_SIZE` | `50` | Events one pass may evaluate |
| `EVENT_LIFECYCLE_SCHEDULER_LOOKBACK_HOURS` | `48` | How far behind the boundary to work |

### Lineup artists

| Variable | Default | Meaning |
| --- | --- | --- |
| `LINEUP_ARTIST_IMPORT_ENABLED` | `true` | Turn announced performers into artists |
| `LINEUP_ARTIST_IMPORT_MAX_ARTISTS` | `100` | Performers one import may create |

A created artist is a stub: name, Songkick id, slug. No `last_synced_at`, so the
sync job is still free to import it and nothing here starts a gigography fetch.
Artist creation and artist import stay separate jobs — which is what keeps a
festival page from costing one outbound request per name on the bill.

### Development safety

Both passes are **off by default**, and neither runs on startup. Starting the API
locally therefore never begins outbound requests to Songkick. Enabling one means
opting a process into making requests on its own account, and nothing does that
implicitly.

### Production

Set `SCHEDULER_ENABLED=true` explicitly, along with the pass you want. In `.env`:

```
SCHEDULER_ENABLED=true
SCHEDULER_INTERVAL_MINUTES=60
ARTIST_SYNC_SCHEDULER_ENABLED=true
ARTIST_SYNC_SCHEDULER_BATCH_SIZE=10
```

`GET /health` reports `scheduler.enabled`, `scheduler.running`,
`scheduler.next_run_at`, and the `lifecycle` and `artist_sync` blocks including
the last run's counters. It reports scheduling facts only — no credentials, no
source URLs, no page content.

### Auditing by hand

Nothing below is scheduled, and the application never invokes any of it. Both
are read-only: they count and sample documents, and neither makes an outbound
request.

```
# A read-only census: missing dates, statuses, festival ranges, lineups.
python -m app.scripts.audit_state

# Which stored events lack what, by field, with examples.
python -m app.scripts.report_event_gaps
python -m app.scripts.report_event_gaps --limit 20
```

There is deliberately no command that goes and fixes what these report. The
enrichment service, its job and the scripts that drove it
(`enrich_events.py`, `recover_incomplete_events.py`) were removed along with
the scheduled pass they belonged to: an import that hands its gaps to a later
reader is only complete if that reader runs, and one that reads on demand is a
second implementation of extraction with a different set of rules. What still
closes a gap is the next catalog refresh, through this same pipeline.

## Safety properties

* **Nothing is deferred.** The import writes, reports, and finishes. No counter
  in its report implies work was handed to a later run, because no such run
  exists.
* **Idempotent.** Every write is a field-level merge of data that is missing. A
  second pass over a finished event writes nothing.
* **Non-destructive.** A stored value is never replaced — including by a resync.
  An import that re-reads a listing without a date will not write that `None`
  over a date an earlier run already obtained, or the record could never settle.
  Attendance belongs to people and is never written by a provider listing either.
* **Bounded.** One scrape reads at most `SONGKICK_EVENT_PAGE_READS_PER_SCRAPE`
  event pages; one tick syncs at most `ARTIST_SYNC_SCHEDULER_BATCH_SIZE`
  artists. Two runs never overlap — if one overruns its interval the next is
  dropped, not queued behind it.
* **Failure tolerant.** An unreachable page, an unreadable response or a rejected
  write is counted where it happened and the run continues.
* **Observable.** Each run logs what it read, what it could not read, what it
  wrote, and which fields were absent from every page — with the event id and
  the source, at the point of occurrence.

## Outcome vocabulary

### The import's report

| Key | Meaning |
| --- | --- |
| `events_created` / `events_existing` / `events_skipped` | What happened to the rows |
| `events_with_extraction_gaps` | Events carrying at least one field no page stated |
| `extraction_gaps` | The same, by field: `date`, `venue`, `lineup` |
| `events_extraction_failed` | The source states a value this run could not read |
| `event_pages_read` | Event pages read to complete this run |
| `event_pages_unread` | Events past the per-run bound, left unread |
| `event_pages_failed` | Pages that did not answer or could not be parsed |
