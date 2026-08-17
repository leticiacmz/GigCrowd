# GigCrowd Design System

## Overview

GigCrowd is a social platform built around live music experiences.

This document defines the visual language, UI patterns, component standards, and implementation rules for the GigCrowd frontend.

The purpose of this design system is to create a consistent experience across the entire application.

The central idea:

> Every concert tells a story.

---

# 1. Design Philosophy

GigCrowd is not a generic social network.

The interface should communicate:

- Live music energy
- Community
- Discovery
- Authentic experiences
- Personal memories

The product should feel closer to:

- Concert posters
- Festival environments
- Stage lighting
- Music communities

Not:

- A generic dashboard
- A Spotify clone
- A standard CRUD application

---

# 2. Visual Identity

## Theme Name

## Neon Stage

A dark interface inspired by:

- Concert stages
- Neon lights
- Festival nights
- Music venues

The visual goal:

Energetic + modern + social.

---

# 3. Color System

## Primary Background

Deep Stage Black

```css
#0F0F12
Usage:

Main application background
Full page surfaces
Surface / Cards

Stage Surface

#18181B

Usage:

Cards
Containers
Panels
Primary Accent

Stage Pink

#FF4D6D

Usage:

Primary actions
Active states
Highlights
Secondary Accent

Electric Purple

#6C63FF

Usage:

Secondary actions
Tags
Decorative elements
Borders

Stage Border

#27272A

Usage:

Card borders
Dividers
Input borders
Typography Colors

Primary:

#FFFFFF

Secondary:

#A1A1AA

Muted:

#71717A
4. Typography
Font

Primary:

Inter

Weights:

300 Light
400 Regular
500 Medium
600 Semi Bold
700 Bold
Scale

Display:

36px

Heading:

28px

Section:

24px

Subtitle:

18px

Body:

16px

Caption:

14px

Small:

12px

5. Layout Principles
Mobile First

GigCrowd users interact with the app:

Before shows
During festivals
After concerts
While discovering artists

The experience must work on mobile first.

Responsive Breakpoints
Mobile

< 640px

Rules:

Single column layouts
Touch-friendly controls
Simplified navigation
Tablet

640px - 1024px

Rules:

Two column layouts
Expanded cards
Optional side content
Desktop

1024px

Rules:

Multi-column layouts
Hover states
Larger content areas
6. Component System

All UI elements should use reusable components.

Do not create duplicated UI patterns inside pages.

Navbar

Purpose:

Main navigation.

Requirements:

Desktop navigation
Mobile navigation
Active state
Dark theme
Consistent spacing
Buttons

Variants:

Primary

Usage:

Main actions

Example:

Follow
Write Review
Attend Event
Secondary

Usage:

Alternative actions

Outline

Usage:

Less emphasized actions

Ghost

Usage:

Navigation and subtle actions

Cards

All cards follow the Stage Card pattern.

Properties:

Dark surface
Rounded corners
Border
Hover transition
Clear hierarchy

Example:

Image

Title

Metadata

Action
Artist Card

Contains:

Artist image
Artist name
Genre
Follow action
Event Card

Contains:

Artist
Date
Venue
Location
Attendance status
Review Card

Contains:

User
Event
Review text
Photos
Interaction actions
Profile Card

Contains:

Avatar
Username
Bio
Statistics
States

All pages must implement:

Loading State

Use skeletons or loading components.

Avoid empty blank screens.

Empty State

Should explain:

What happened
What user can do next

Example:

No concerts yet.

Discover your next show.
Error State

Must provide:

Clear message
Retry option when possible
7. Page Structure
Home Feed

Purpose:

Community experience.

Contains:

Friends activity
Reviews
Concert memories
Discoveries
Artist Pages

Route:

/artists/[slug]

Structure:

Artist Header

Image

Name

Genre

Follow Button


Tabs:

Events
Reviews
About
Events Tab

Shows:

Upcoming concerts:

Next events
Venue
Date
Location

Past concerts:

Previous performances
Community memories
Reviews Tab

Contains:

Fan experiences
Photos
Stories
About Tab

Contains:

Biography
Artist information
Event Page

Contains:

Artist
Date
Venue
Location

Community:

Fans attending
Reviews
Photos
User Profile

Contains:

User identity
Concert history
Reviews
Musical journey
8. Implementation Rules
IMPORTANT

This design system is not only a visual reference.

The goal is to migrate the existing application to use these standards.

Creating components alone is not considered complete.

Migration Requirements

A successful implementation requires:

Components

✅ Components created

AND

✅ Existing pages using those components

Pages

Existing pages must be updated to follow:

Colors
Typography
Spacing
Components
Responsive rules
Avoid

Do not:

Create duplicate components
Leave old UI patterns behind
Build parallel implementations
Only change colors without updating structure
9. Existing Code Protection Rules

When modifying existing files:

Preserve business logic
Preserve API integrations
Preserve authentication flows
Preserve existing functionality
Avoid unnecessary rewrites

Prefer:

Small incremental changes.

Avoid:

Large destructive replacements.

10. Development Workflow

For every implementation phase:

Step 1

Analyze current implementation.

Identify:

Existing components
Existing pages
Required changes
Step 2

Plan changes.

Define:

Files affected
Components reused
New components required
Step 3

Implement incrementally.

Rules:

One logical change at a time
Keep application running
Verify after changes
Step 4

Validate.

Check:

Visual consistency
Responsive behavior
No broken functionality
11. Definition of Done

A feature is considered complete only when:

Visual

✅ Matches Design System

✅ Responsive

✅ Uses shared components

Technical

✅ Existing functionality preserved

✅ No duplicated patterns

✅ Build passes

Product

✅ Feels like GigCrowd

✅ Supports the live music experience

12. Future Opportunities

Possible future improvements:

Festival Mode

Support:

Festival schedules
Lineups
Multi-day events
Concert Timeline

Personal history:

"Your live music journey"

AI Memories

Generate:

Concert summaries
Year reviews
Personal music stories
Related Documentation

Development workflow and AI-assisted engineering practices:

AI_DEVELOPMENT_GUIDE.md

Architecture documentation:

ARCHITECTURE.md

API documentation:

API.md
Final Principle

GigCrowd is not a database of concerts.

It is a collection of human experiences around music.

Every interface decision should reinforce that idea.