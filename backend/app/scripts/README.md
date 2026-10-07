# Development scripts

Scripts that act on the local development database. Every one of them refuses
to run against anything but a loopback address.

```
python -m app.scripts.reset_dev_db          # what would be dropped
python -m app.scripts.reset_dev_db --apply  # drop it, recreate indexes
python -m app.scripts.seed_dev_data          # what would be written
python -m app.scripts.seed_dev_data --apply  # write the dataset
```

Order matters: reset, then seed.

## The safety guard

`reset_dev_db` is the only code in the project that deletes data, so proving
what it is pointed at is the whole job. Three conditions must all hold before it
drops anything, and it exits non-zero with an explanation if any fails:

1. `MONGODB_URL` parses as a MongoDB URI whose host is `localhost`, `127.0.0.1`
   or `::1`. A hostname, a LAN address, or `mongodb+srv://` is refused.
2. `DATABASE_NAME` is one of `gigcrowd`, `gigcrowd_dev`, `gigcrowd_test`.
3. `--apply` was passed. There is no "just do it" path.

`seed_dev_data` uses the same guard, because it writes passwords.

The host check is an exact match rather than a substring: `localhost.attacker.example`
is not localhost, and a naive `in` test would accept it.

## Indexes

Indexes are declared once, in `app/database/indexes.py`, and created:

* at application startup, so a fresh database is usable immediately;
* by the reset script, so a wiped database is not left indexless;
* by the seed script, so seeding into a partial database completes it.

The uniqueness rules there are part of the data model, not tuning. In particular
`artists.external_ids.songkick` is unique and sparse: it is what stops a second
import from creating a duplicate artist that merely happens to share a provider
id, and it is the rule that keeps the Arctic Monkeys duplicate from recurring.

## The seed dataset

A small, coherent fixture rather than a copy of old data.

| Collection | What it covers |
| --- | --- |
| `users` | Four, including one who follows nobody and has logged nothing |
| `artists` | Real Spotify / Songkick / MusicBrainz ids; one deliberately thin |
| `venues` | Four, with real coordinates |
| `events` | Past, future, multi-day, festival dates with lineups |
| `show_logs` | All three attendance states |
| `follows` | Someone who follows, and someone who is followed |
| `artist_follows` | Including an artist followed but never attended |
| `community_posts` | Across several artists, with comments and likes |
| `posts` | A post about a specific event |
| `activities` | Reviews, attendance and community activity |
| `notifications` | Comment and follow |

Three properties make it usable as a fixture:

**Deterministic.** Every document is built from this module's constants and every
date derives from one `ANCHOR` rather than the clock. Two runs produce
byte-identical documents.

**Idempotent.** Each document carries a `_id` derived from its logical name, so
a re-run replaces rather than appends, and reports zero writes.

> Reaching true idempotency took two fixes that are worth knowing about.
> BSON has no timezone, so MongoDB returns naive datetimes and a document
> written with an aware value never compares equal to itself; the client now
> connects with `tz_aware=True`. And `_id` must be the first key of a
> replacement, because MongoDB always stores it first and a replacement with it
> last is a different byte encoding of an identical document - which the driver
> reports as changed.

**Local only**, enforced by the guard above.

### The fixture password

Every seeded user **except the two controlled accounts** has the password
**`gigcrowd-dev-2024`**, sign in through the login form using the address form of
the email (`leticia@gigcrowd.app`) because the login route matches on email.

| Username | Email | History |
| --- | --- | --- |
| `leticiacmz` | `leticia@gigcrowd.app` | Full: 8 attended across 2 years, 2 going, 2 maybe |
| `brunor` | `bruno@gigcrowd.app` | Partial, and owns his own review |
| `analima` | `ana@gigcrowd.app` | Partial, follows Leticia |
| `theov` | `theo@gigcrowd.app` | Empty |

Plus two **controlled accounts**, which are the exception to the shared password
and the reason for it:

| Username | Email | Password |
| --- | --- | --- |
| `testuser1` | `testuser1@gigcrowd.app` | `GigCrowd-Test-2026!A` |
| `testuser2` | `testuser2@gigcrowd.app` | `GigCrowd-Test-2026!B` |

They have separate passwords on purpose. A shared fixture password cannot do
their job: handing it to somebody authenticates whichever account the login route
matched first, so a check written against "testuser1" would silently be testing
"testuser2".

### Every seeded Songkick id is real, and that took checking

Six of the eight Songkick ids this fixture previously held did not resolve. The
artists looked perfectly normal in the database and every page for them answered
"Songkick artist page error: 410" — a seeded id that does not resolve is worse
than no id, because it looks correct in the document and produces a broken page.

They now live in one named table, `SONGKICK_IDS`, each confirmed by fetching the
artist's own page, and the fixture tests assert the table so a drift is caught
there rather than by somebody opening a page.

The single exception is named `INVENTED_SONGKICK_ID` and belongs to "Victo", an
artist that does not exist. It is there so a page can be judged when the
catalogue knows almost nothing about an artist, and so the failed-initialization
path has something to happen to.

### The catalogue stays small, on purpose

Eight artists, four venues, thirteen events. The limits are asserted by the
fixture tests, and they are not taste: this project once grew a catalogue of
several thousand artists created by walking historical festival lineups, and the
result was a database where nobody could say where a row came from. A
development fixture has the opposite job.

### What the fixture deliberately contains

* **Attendance in `maybe`.** Real data had never held one, so its empty state was
  all that had ever been seen of it.
* **One act twice on one bill.** This is the row that proves a per-show count
  cannot double-count.
* **One artist on several attended shows.** This is what makes "3 shows" a
  statement about shows rather than about lineups.
* **A festival series with three editions.** Identity and edition cannot be
  confused when there is more than one of them.
* **Artists of differing completeness.** A seed where every artist is complete
  cannot show how a page behaves when one is not.
* **No `follow` activities.** A follow is a relationship mutation, not something
  to read about in a timeline.

## Other scripts

| Script | Purpose |
| --- | --- |
| `backup_dev_db.py` | JSON dump of every collection, before a reset |
| `audit_state.py` | Read-only census of events, lineups, attendance, artists |
| `audit_lineup_artist_identities.py` | Whether the identities lineup expansion created are real |
| `report_lineup_resolution.py` | How much of the stored lineup can be linked |
| `report_event_gaps.py` | Which events are incomplete, without fetching |
| `enrich_events.py` | Fill missing event fields from the provider |
| `recover_incomplete_events.py` | Drain the incomplete backlog through the scheduler's own job |
| `import_lineup_artists.py` | Make the artists already stored in lineups real artists |

`report_lineup_resolution.py`, `audit_state.py` and
`audit_lineup_artist_identities.py --report` are read-only and safe to run at any
time.

### Auditing the identities lineup expansion created

Walking a festival's lineup used to write an `Artist` per name, from a number
parsed off the poster's page, with nothing checking that the number addressed
whoever the name beside it said. Roughly 8,000 such records exist. They are not
obviously wrong — each has a plausible name and a real-looking id — which is
exactly why the question has to be settled against Songkick rather than by
looking at the stored document.

`audit_lineup_artist_identities` fetches the artist's own page for each record
and records what Songkick actually served, into a collection of its own. It
deletes nothing, never re-addresses an artist (a slug is a URL other people's
links already point at), and writes only the canonical name and photograph of a
confirmed identity — under `--apply`, as a separate and explicit step.

Songkick serves one page per request, so a full pass is a multi-hour job. The
run is therefore bounded by `--limit` and resumable: the verdict log records
what has already been checked, so a second run continues rather than restarting.

```
python -m app.scripts.audit_lineup_artist_identities --limit 500
python -m app.scripts.audit_lineup_artist_identities --report
python -m app.scripts.audit_lineup_artist_identities --apply
```

A record whose page could not be *read* is reported as unreadable rather than
refused: a timeout is not evidence about an identity, and counting it as one
would permanently skip a real artist.

### Nothing here is needed to keep imports correct

The two scripts at the bottom exist to look at the catalogue and to bring
*existing* records forward. They are not part of the import lifecycle:

* An import enriches its own incomplete events through
  `EventEnrichmentService.enrich_event`. See `app/jobs/README.md`.
* A scheduler tick catches whatever an import deferred or failed on, through the
  same service.
* `recover_incomplete_events.py` calls `run_enrichment_once` — exactly what the
  scheduler calls — in a loop, because one tick is deliberately bounded. It is
  the scheduler's job with more ticks, not a different job.

```
# What is still incomplete, and why.
python -m app.scripts.recover_incomplete_events --dry-run
python -m app.scripts.recover_incomplete_events --apply

# Lineups stored before announced performers became artists.
python -m app.scripts.import_lineup_artists --dry-run
python -m app.scripts.import_lineup_artists --apply
```

Both create artist and event records and nothing else: no gigography is fetched
and no `last_synced_at` is written, so importing an artist stays the sync job's
decision rather than a side effect of reading a page.

### The loopback guard

Only `reset_dev_db` and `seed_dev_data` refuse to run against a non-loopback
MongoDB. The scripts above write only by merging fields that are missing and by
creating artists keyed on a provider id, so they are idempotent by construction
and are safe to point at a real catalogue — but read them first.

