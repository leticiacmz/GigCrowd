"""Background job infrastructure.

`EventEnrichmentService` knows how to fill in a missing event field.
`enrichment_job` knows how to walk a bounded batch of incomplete events.
`scheduler` knows when to do that, and only when configuration has asked it to.

The dependency runs one way: scheduler -> job -> service. Nothing in the job
or the service imports the scheduler, so a scheduled run and a manual one
execute exactly the same code.
"""
