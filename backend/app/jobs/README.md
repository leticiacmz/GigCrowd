# Background jobs

There is exactly one scheduler in this project and it is `scheduler.py`. It owns
a clock and nothing else.

## The lifecycle

An imported event is not trusted to be complete just because the listing was
read. Songkick's gigography names festival dates **without dating them**, while
each of those dates has a page of its own carrying the real `startDate` and
`endDate`. Measured on a single artist: 41 of 45 festival entries arrived with
no date at all.

So there are two passes over the same work, not two implementations of it:

```
Songkick gigography
    ↓
event created                              ← SongkickEventImportService
    ↓
if still incomplete  ── yes ──→ read the concrete event page, right now
    ↓ no                                  ← EventEnrichmentService.enrich_event
event persisted
...
later, on a tick
    ↓
scheduler catches anything deferred or failed
    ↓                                        ← EnrichmentScheduler
```

Both arrows land in `EventEnrichmentService`, and both go through the same
`_plan_for`, the same `apply_patch` and the same date helpers. There is one
implementation of "what is missing" and one implementation of "what is safe to
write", so a record enriched during an import and one enriched by the scheduler
cannot disagree about either.

The import is the normal path. The scheduler is the safety net, not the routine.

| Stage | Entry point | Bounded by |
| --- | --- | --- |
| During import | `SongkickEventImportService` → `enrich_event` | `ENRICH_ON_IMPORT_MAX_EVENTS` |
| On a tick | `EnrichmentScheduler` → `run_enrichment_once` | `ENRICHMENT_SCHEDULER_BATCH_SIZE` |

The import reports what it could not do: `events_enriched`,
`events_enrichment_failed` and `events_enrichment_deferred`. Anything deferred is
the scheduler's next tick, by construction rather than by hope.

### Measured

One real `SynchronizationService.synchronize_artist` call, one artist:

```
[EVENT IMPORT] Reading the concrete source for 41 incomplete event(s); 0 deferred
[EVENT IMPORT] 🔎 Events read at source during import: 41
[EVENT IMPORT] ⚠️ Enrichment failures (scheduler will retry): 0
[EVENT IMPORT] ⏳ Deferred to the scheduler: 0
```

Forty-one events that had been written with `starts_at = null` and
`date_status = null` left that one call dated, their festival ranges intact, and
the source checked. Nothing ran afterwards. The same sync also re-read an artist
whose 40 previously recovered dates it re-listed as undated, and left all 40
alone — see the resync rule under [Safety properties](#safety-properties).

```
scheduler.py        when a pass runs
    ↓
enrichment_job.py   what one pass does
    ↓
EventEnrichmentService   which events are worth a visit, and what may be written
    ↓
SongkickClient            reads the provider's page
    ↓
MongoDB                   field-level merge of what was missing
```

The dependency runs one way. Neither the job nor the service imports the
scheduler, so a scheduled pass and a manually triggered one execute exactly the
same code.

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

## What a pass enriches

Selection is the enrichment service's, not the scheduler's.
`EventEnrichmentService.plan()` answers "which events would gain something from a
source visit", and the scheduler passes through the configured field mode:

| Mode | What it chases | Needs `INCLUDE_DATED` |
| --- | --- | --- |
| `dates` | Events with no date, or whose date could not be parsed | no |
| `lineup` | Festival dates with no lineup | yes |
| `location` | Events with no location | yes |
| `all` | Anything above | yes |

Nothing else is retried. A record that is already complete is not selected at
all, so a steady-state run costs one indexed query and zero requests.

### What "incomplete" means

One definition, `EventEnrichmentService.is_incomplete()`, used by both the
import and the scheduler so they cannot drift apart. An event is incomplete when:

* it has no `starts_at` — it cannot be placed in time at all
* it has no `date_status` — nothing has claimed to know, and **unknown is not
  `unavailable`**
* its `date_status` is `parser_failed`
* its `date_status` is `unavailable` with **no** `date_source_checked_at`
* it is missing a location or a festival lineup, when that field was asked for

Two things deliberately do *not* count:

* **A concert with a start and no end.** A gig starts and it is over; Songkick
  states no end for it. Treating the absent end as a gap would send a pass to
  every concert ever imported, on every tick, to find nothing.
* **An event whose source was read and genuinely had no date.** That is an
  answer, not a gap.

### `unavailable` only counts once it has been earned

`date_source_checked_at` is written by a real source visit, and `unavailable` is
only believed when that marker is beside it.

This is the distinction the whole lifecycle rests on. `unavailable` written by the
importer from a listing that merely carried no date is a guess, and the selector
used to take it at face value — so fifty festival dates whose dates were sitting
on Songkick the whole time were never re-read. A listing that says nothing is not
a finding, and now reads as what it is: unknown.

## Configuration

### During import

| Variable | Default | Meaning |
| --- | --- | --- |
| `ENRICH_ON_IMPORT_ENABLED` | `true` | Read the concrete source during an import |
| `ENRICH_ON_IMPORT_FIELDS` | `dates` | `dates`, `lineup`, `location` or `all` |
| `ENRICH_ON_IMPORT_MAX_EVENTS` | `1000` | Incomplete events one import may re-read |
| `ENRICH_ON_IMPORT_DELAY_SECONDS` | `1.5` | Pause between source requests |

On by default, because it is the normal path rather than an extra. Turning it off
only moves the work to the scheduler and leaves the record incomplete in the
meantime.

### The safety net

| Variable | Default | Meaning |
| --- | --- | --- |
| `ENRICHMENT_SCHEDULER_ENABLED` | `false` | Whether the scheduler runs at all |
| `ENRICHMENT_SCHEDULER_INTERVAL_MINUTES` | `360` | Minutes between passes |
| `ENRICHMENT_SCHEDULER_BATCH_SIZE` | `25` | Events one pass may attempt |
| `ENRICHMENT_SCHEDULER_REQUEST_DELAY_SECONDS` | `1.5` | Pause between source requests |
| `ENRICHMENT_SCHEDULER_FIELDS` | `dates` | `dates`, `lineup`, `location` or `all` |
| `ENRICHMENT_SCHEDULER_INCLUDE_DATED` | `false` | Also revisit already-dated events |
| `ENRICHMENT_SCHEDULER_RUN_ON_STARTUP` | `false` | Run one pass immediately on boot |

### Artist synchronization

| Variable | Default | Meaning |
| --- | --- | --- |
| `ARTIST_SYNC_SCHEDULER_ENABLED` | `false` | Import gigographies for stale artists |
| `ARTIST_SYNC_SCHEDULER_INTERVAL_MINUTES` | `360` | Minutes between passes |
| `ARTIST_SYNC_SCHEDULER_BATCH_SIZE` | `10` | Artists one pass may sync |
| `ARTIST_SYNC_TTL_HOURS` | `24` | How old a sync may be |

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

Both schedulers are **off by default**, and neither runs on startup. Starting the
API locally therefore never begins outbound requests to Songkick. Enabling one
means opting a process into making requests on its own account, and nothing does
that implicitly. Enrichment *during an import* is different: it is on by default
because an import is already an explicit request to talk to Songkick, so the
extra page fetches are within what was asked for.

### Production

Set `ENRICHMENT_SCHEDULER_ENABLED=true` explicitly. In `.env`:

```
ENRICHMENT_SCHEDULER_ENABLED=true
ENRICHMENT_SCHEDULER_INTERVAL_MINUTES=60
ENRICHMENT_SCHEDULER_BATCH_SIZE=25
ENRICHMENT_SCHEDULER_REQUEST_DELAY_SECONDS=1.5
ENRICHMENT_SCHEDULER_FIELDS=dates
```

`GET /health` reports `scheduler.enabled`, `scheduler.running`,
`scheduler.next_run_at` and the counters from the last pass. It reports
scheduling facts only — no credentials, no source URLs, no page content.

### Auditing and recovering by hand

Both are for looking at the state of the catalogue, not for keeping it correct.
Nothing here needs to be run for a new import to come out complete.

```
# A read-only census: missing dates, statuses, festival ranges, lineups.
python -m app.scripts.audit_state

# The scheduler's own job, in a loop, because one tick is deliberately bounded.
# Not a second implementation - it calls run_enrichment_once, which is exactly
# what EnrichmentScheduler calls on every tick.
python -m app.scripts.recover_incomplete_events --dry-run
python -m app.scripts.recover_incomplete_events --apply

# The single-pass CLI, for a one-off.
python -m app.scripts.report_event_gaps
python -m app.scripts.enrich_events --dry-run --limit 25
python -m app.scripts.enrich_events --apply --limit 200 --delay 1.5
```

To recover a specific field, set the mode and turn on dated events:

```
python -m app.scripts.enrich_events --apply --fields lineup --include-dated
python -m app.scripts.enrich_events --apply --fields location --include-dated
```

## Safety properties

* **Idempotent.** Every write is a field-level merge of data that is missing. A
  second pass over a finished event writes nothing and reports `unchanged`.
* **Resumable.** A record that failed is still a candidate next pass. Nothing is
  checkpointed, because nothing needs to be: selection is derived from the
  current state of the database.
* **Rate limited.** One pass is bounded by `batch_size`, and requests are paced
  by the delay. Two passes never overlap — if one overruns its interval the next
  is dropped, not queued behind it.
* **Failure tolerant.** An unreachable page, an unreadable response or a
  rejected write is counted and the run continues.
* **Non-destructive.** A stored value is never replaced — including by a resync.
  An import that re-reads a listing without a date will not write that `None`
  over a date enrichment already recovered, or the recovery would be
  self-erasing and the record could never settle. Attendance belongs to people
  and is never written by a provider listing either.
* **Observable.** Each pass logs what it selected, attempted, updated, left
  unchanged, could not read, could not parse, could not fetch, and could not
  write.

## Outcome vocabulary

`EnrichmentJobResult` counts these separately, because "nothing happened" and
"everything failed" are different problems:

| Counter | Meaning |
| --- | --- |
| `selected` | Events `plan()` judged worth a visit |
| `attempted` | Events whose source was actually read |
| `updated` | Fields written |
| `unchanged` | Source read, but it had nothing to add |
| `source_missing` | No stored page URL, so it can never be re-read |
| `parse_failed` | Page read, but no usable structured data |
| `request_failed` | The provider could not be reached |
| `write_failed` | The database rejected the write |
| `missing_record` | The row disappeared between selection and the visit |

An import reports the same ideas as `events_incomplete_found`,
`events_enriched`, `events_enrichment_failed` and `events_enrichment_deferred`.

