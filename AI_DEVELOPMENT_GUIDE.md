# AI Development Guide - GigCrowd

## Overview

GigCrowd is a social platform built around live music experiences.

The purpose of this document is to define how Artificial Intelligence should be used during the development lifecycle of the project, helping maintain code quality, architectural consistency, and product vision.

AI is considered a development assistant, not a replacement for engineering decisions.

The final responsibility for architecture, security, performance, and product decisions remains with the developer.

---

# 1. AI Development Philosophy

The main goal of using AI in GigCrowd development is:

- Increase development speed
- Reduce repetitive work
- Improve code quality
- Support architectural decisions
- Generate documentation
- Assist with debugging
- Explore alternative solutions

AI should help developers think better, not simply generate code faster.

---

# 2. Project Context

Before generating code, AI must understand the following project principles.

## Product Vision

GigCrowd is a social network for music fans.

The idea is similar to how platforms like Letterboxd organize movie experiences, but focused on concerts.

Users should be able to:

- Discover artists
- Track attended shows
- Share concert experiences
- Follow other fans
- Review performances
- Build a personal concert history

The central concept:

> Every concert tells a story.

---

# 3. Core Architecture Context

## Backend

Technology:

- Python
- FastAPI
- MongoDB
- Motor
- Pydantic
- RabbitMQ
- AWS S3

Architecture principles:

- Domain-driven organization
- Separation between providers, services, repositories, and routes
- Business rules should not depend on external APIs

Structure example:
app/
├── domain/
├── repositories/
├── services/
├── providers/
├── routes/
├── schemas/
└── infrastructure/


---

# 4. External Integrations

GigCrowd currently integrates with:

## Spotify

Purpose:

- Artist search
- Artist metadata
- Images
- Biography information

Important:

Spotify follower counts must not be exposed as public social metrics.

GigCrowd follows its own internal relationship system.

---

## Bandsintown

Purpose:

- Concert discovery
- Upcoming events
- Event synchronization

Bandsintown is responsible only for event data.

---

# 5. AI Coding Rules

When generating code, AI should follow these rules:

## Always respect existing architecture

Do not introduce:

- New frameworks without discussion
- New patterns without justification
- Duplicate business logic

---

## Prefer complete files

When modifying existing code:

Provide complete updated files whenever possible.

Avoid isolated snippets that require manual merging.

---

## Keep domain logic independent

Example:

Bad:


ArtistService -> Spotify API directly


Good:


ArtistService
|
Provider Interface
|
Spotify Provider


---

# 6. Code Quality Standards

Generated code should prioritize:

## Readability

Prefer:

- Clear names
- Small functions
- Explicit logic

Avoid:

- Complex one-liners
- Hidden behavior
- Premature optimization

---

## Testing

Important areas:

- Services
- Providers
- Authentication
- Synchronization flows
- Data mapping

Example:


test_artist_import_service.py
test_spotify_provider.py
test_event_mapper.py


---

# 7. AI Assisted Development Workflow

Recommended workflow:

## Step 1 - Understand

Before coding:

- Explain the problem
- Identify affected layers
- Confirm expected behavior

---

## Step 2 - Design

Define:

- Data flow
- Responsibilities
- Files affected
- Possible risks

---

## Step 3 - Implement

Generate:

- Complete files
- Tests
- Documentation updates

---

## Step 4 - Review

Ask AI to review:

- Architecture
- Security
- Edge cases
- Naming
- Performance

---

# 8. Database Principles

MongoDB collections:


artists
events
venues
users
posts
reviews
comments
follows
show_logs


Important rules:

## External data is not social data

Example:

Spotify followers:


spotify_followers


should not become:


GigCrowd followers


GigCrowd relationships are controlled by:


follows


## An identifier is not an identity

A number parsed off a page names *something*. Whether it names the thing you
think it does has to be checked against the page it addresses, before anything
is written, and the check has to be allowed to pass.

Both halves matter, and the second is the one that gets forgotten.

**Do not accept an unchecked id.** Songkick reassigns ids; a venue page and an
artist page share a numeric shape; a lineup entry carries whatever id the poster
happened to link. Creating an `Artist` from such an id is permanent, is linkable
from every festival that announced the name, and records nothing about whether
the identity was ever checked. `SongkickArtistVerifier` runs before the write.

**Do not refuse a real artist.** Songkick does not render every artist page the
same way. Most carry an `<h1>` naming the artist; some carry none at all — The
Coronas and The Stranglers, checked against the live site, state their name only
in structured data and in the document title. A reader that treats the heading as
mandatory refuses two real, touring, festival-announced acts and reports nothing
wrong while doing it, because a false refusal *loses* an artist rather than
corrupting one. Sources are consulted strongest-first and none of them is
mandatory: see `app/domain/artist_page_statement.py`.

The general form: **a validation rule that has only ever been seen rejecting
obviously-bad input has not been tested.** It may also be rejecting the truth,
and that direction is invisible from the output.

## An artist is not a gigography

Knowing *who* an artist is says nothing about *when they play*. The two are
separate, and conflating them is how a catalogue fills with permanent records
that nothing will ever populate:

- Lineup membership creates an `Artist` and never an `Event`. Being on a bill is
  not a performance date.
- A festival *edition* is the event — the festival, its dates, its venue. An
  artist has one night of it, and the festival's range is never stored as that
  artist's show.
- `last_synced_at` is written only by a sync that actually fetched gigography.
  Its absence is what marks an artist as still importable, so a validation pass
  must not stamp it.

## Exactly one page load may write

`GET /artists/{slug}` is read-only **except** on the first open of a pending
artist, where it is also the moment that artist is initialized.

Everything else about a page load stays a read. An *initialized* artist — including
one whose synchronization previously failed — is never re-fetched by a view,
because a page that scrapes a provider is what made this application's artist
pages slow, expensive and impossible to reason about: the catalogue depended on
who happened to look, one request could spend an unbounded number of calls, and
opening a page wrote rows nobody asked it to write.

The distinction is the artist's state, and it is checked *before* anything is
fetched rather than after:

| State | What a GET does |
| --- | --- |
| pending — identity known, never fetched | may initialize, exactly once, under a claim |
| error — a fetch was attempted and failed | may retry, on a cooldown, not on every view |
| initialized — including mid-claim | read-only, every time |

`app/domain/artist_state.py` owns those three states, derived from `sync_status`
and `last_synced_at`. Do not add a parallel availability field beside them: two
sources of truth for one fact, and the one nobody remembers to update is the one
that decides whether a page performs a gigography scrape.

**The first open is slow, and that is the design.** A cold artist took 42 seconds
against the live provider. Every open after that is instant. If you find yourself
wanting to make it faster, the honest options are an import-progress indicator or
an asynchronous import — not dropping the initialization, which is what makes a
lineup artist's page show a discography instead of an apology.

## Two paths may initialize; the scheduler may not

An artist is initialized when a person imports them or opens their page. There is
no third trigger. `ArtistSyncJob` is maintenance — it refreshes artists that
already have a gigography and have aged past the TTL — and its selection query
requires positive evidence that a fetch already happened.

That is not a tuning decision. "Never-synced is eligible" was how the scheduler
used to drain thousands of announced-but-unopened artists: the batch filled with
the same cold rows every hour, and nobody who actually followed an artist ever
got refreshed.

---

# 9. AI and Product Decisions

AI can help evaluate:

- UX improvements
- Feature ideas
- Technical alternatives

However:

Product decisions must prioritize:

1. User experience
2. Project vision
3. Simplicity
4. Maintainability

---

# 10. Future AI Opportunities

Possible future integrations:

## Personalized Recommendations

AI could recommend:

- Artists
- Concerts
- Festivals

based on:

- Listening history
- Attended shows
- Reviews
- Follow relationships

---

## Concert Memory Assistant

After an event:

AI could help users create:

- Reviews
- Memories
- Summaries

Example:

"Tell us how the show was."

---

## Smart Feed Ranking

Future feed ranking could consider:

- Friends activity
- Artists followed
- Previous attendance
- Music preferences

---

# 11. Security Guidelines

AI-generated code must always consider:

- Authentication
- Authorization
- Input validation
- Secrets management
- API limits

Never expose:

- Tokens
- API keys
- Private user information

---

# 12. Documentation Requirement

Every significant feature should update documentation.

Examples:


docs/
├── architecture.md
├── design.md
├── api.md
└── ai_development.md


Good documentation is part of the product.

---

# Final Principle

AI is a collaborator inside the GigCrowd development process.

The goal is not to write more code.

The goal is to build a better product.

# Frontend Design System Requirement

All frontend development must follow:

DESIGN_SYSTEM.md

The Design System is the source of truth for:

- Colors
- Typography
- Layout
- Components
- UI patterns
- Responsive behavior
- User experience decisions

Any new frontend feature must:

- Reuse existing design system components.
- Follow established visual patterns.
- Avoid creating independent UI solutions.
- Update the design system when introducing new patterns.