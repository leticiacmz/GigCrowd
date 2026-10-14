"""Background job infrastructure.

`artist_sync_job` knows how to walk a bounded batch of stale artist catalogues,
and every event it discovers or refreshes goes through the same extraction
pipeline a manual sync runs. `scheduler` knows when that pass and the event
lifecycle pass run, and only when configuration has asked it to.

There is no pass over incomplete events anywhere in this package. A field an
extraction could not obtain is reported by the import, in the run that found
it, with the event id and the field; nothing is queued for a later process to
chase. The manual enrichment service, job and scripts that used to live here
have been removed: they only ever existed to be the other half of an import
that deferred its own gaps.

The dependency runs one way: scheduler -> job. Nothing in a job imports the
scheduler, so a scheduled run and a manual one execute exactly the same code.
"""
