# 🎵 GigCrowd

### Every concert tells a story.

GigCrowd is a social platform for live music enthusiasts, designed to bring the entire concert experience together in one place.

Inspired by the event discovery experience of **Facebook Events** and the social cataloging of **Letterboxd**, GigCrowd helps people discover concerts, build their concert history, and connect through unforgettable live music experiences.

> 🚧 **Work in progress** — actively under development.
<br>


## 🎯 The Problem

Live music fans constantly switch between different platforms to:

- 🎫 Discover concerts
- ❤️ Follow favorite artists
- 📅 Keep track of upcoming events
- 📸 Save memories
- 👥 Connect with friends
- 🎶 Remember every concert they've attended

There isn't a platform focused on the complete live music journey.


## 🚀 The Solution

GigCrowd brings every part of the concert experience into a single platform.

Whether you're discovering your next show, tracking every concert you've attended, or sharing unforgettable memories with friends, GigCrowd aims to become the home for live music fans.

<br>

## ✨ Features

### 🎫 Concert Discovery

Discover concerts through integrated event providers and explore artists, venues, and upcoming live events.


### 🎵 Concert History

Build your personal concert timeline and keep a record of every unforgettable live experience.


### ❤️ Favorite Artists

Follow your favorite artists and never miss upcoming concerts.


### 👥 Social Platform

Connect with friends, discover what they're attending, and share your own concert experiences.


### 📸 Concert Memories

Create posts, upload photos, and preserve the memories behind every show.


### 🤖 Personalized Recommendations *(Planned)*

Receive recommendations based on your favorite artists, music preferences, attendance history, and community activity.
<br>

## 🏗 Architecture

GigCrowd is being built with a modern, scalable architecture focused on maintainability and performance.

```text
                 Next.js + React
                        │
                        ▼
                 FastAPI Backend
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
    MongoDB        RabbitMQ      External APIs
                                      │
                         Spotify • Bandsintown
```


## 🛠 Tech Stack

### Frontend

- Next.js
- React
- TypeScript
- Material UI

### Backend

- Python
- FastAPI
- JWT Authentication

### Database

- MongoDB

### Infrastructure

- Docker
- RabbitMQ
- AWS

### External Integrations

- Spotify API
- Bandsintown API

<br>

## 🗺 Roadmap

### ✅ Completed

- JWT Authentication
- User Profiles
- Artist Search
- Spotify Integration
- Bandsintown Integration
- Artist Import Pipeline
- Follow System
- REST API Foundation

### 🚧 In Progress

- Artist Profile
- Activity Feed
- Concert Attendance
- Social Posts
- Media Upload
- Event Timeline

### 💡 Planned

- Spotify Authentication
- Personalized Recommendations
- Festival Tracking
- Concert Wishlist
- Notifications
- Mobile Application

<br>

## ❤️ Why GigCrowd?

GigCrowd started from a simple frustration.

As someone who loves going to concerts, I realized there wasn't a platform built specifically for people who enjoy live music.

Most existing services focus on selling tickets or listing events, but none truly capture the entire experience: discovering concerts, remembering every show, sharing memories, and connecting with people who were there.

GigCrowd was born to change that.

<br>

## 🌱 Current Status

GigCrowd is currently under active development.

This repository documents the project's evolution, architectural decisions, and ongoing implementation as new features continue to be added.

<br>

## 🤝 Contributing

Suggestions, ideas, and feedback are always welcome.

If you'd like to contribute, report a bug, or discuss new features, feel free to open an issue or submit a pull request.

<br>

## 🔮 Vision

GigCrowd aims to become the go-to platform for live music enthusiasts.

Instead of relying on multiple apps to discover concerts, track attendance, organize memories, and connect with friends, users will have a single place dedicated to their entire live music journey.

Because every concert tells a story.

**GigCrowd is where those stories live.**

<br>

<p align="center">

Made with ❤️ by <b>Leticia Cruz</b>

</p>
