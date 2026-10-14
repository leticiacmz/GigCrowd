# 🎵 GigCrowd

### Every concert tells a story.

**GigCrowd is a social platform for live music enthusiasts**, bringing concert discovery, artist tracking, attendance history, and community experiences together in one place.

Inspired by the event discovery experience of Facebook Events and the social cataloging of Letterboxd, GigCrowd aims to help people discover live music, document their concert journeys, and connect through the experiences that bring us together.

<p align="center">

**🌐 [Visit GigCrowd](https://YOUR-VERCEL-DOMAIN)** · **⚡ [API](https://gigcrowd-api.onrender.com/)** · **📚 [API Documentation](https://gigcrowd-api.onrender.com/docs)**

</p>

> 🚧 **Status: Under active development.** Features, interfaces, and API endpoints may change as the project evolves.

---

## 🌐 Try GigCrowd

Explore the deployed application and its API without cloning the repository.

| Resource                                                             | Description                                  |
| -------------------------------------------------------------------- | -------------------------------------------- |
| **[GigCrowd Website](https://YOUR-VERCEL-DOMAIN)**                   | Explore the live platform.                   |
| **[API Base URL](https://gigcrowd-api.onrender.com/)**               | Check whether the backend is responding.     |
| **[Swagger UI](https://gigcrowd-api.onrender.com/docs)**             | Explore and interact with the REST API.      |
| **[ReDoc](https://gigcrowd-api.onrender.com/redoc)**                 | Browse the API reference.                    |
| **[Health Check](https://gigcrowd-api.onrender.com/health)**         | Check the API and scheduler status.          |
| **[OpenAPI Schema](https://gigcrowd-api.onrender.com/openapi.json)** | Access the API specification in JSON format. |

### How to test the API

1. Open the [Swagger documentation](https://gigcrowd-api.onrender.com/docs).
2. Expand an endpoint to inspect its parameters and response schema.
3. Click **Try it out**, provide the required parameters, and execute the request.
4. Inspect the HTTP status code and response body.

Some endpoints require authentication. Use test data and avoid submitting personal information or real credentials.

*Note: The first request may take longer if the hosting service needs to wake up.*

---

## 🎯 The Problem

Live music fans often rely on multiple platforms to:

* 🎫 Discover concerts and festivals.
* ❤️ Follow their favorite artists.
* 📅 Keep track of upcoming events.
* 🎟️ Record concerts they've attended.
* 📸 Save photos and memories.
* 👥 Connect with people who share their musical interests.

Most platforms focus on individual parts of this experience. GigCrowd explores how to bring the entire live music journey together.

## 🚀 The Solution

GigCrowd combines event discovery, artist tracking, concert history, and social interaction into a platform dedicated to live music.

Whether you're looking for your next show, keeping track of the artists you love, or preserving memories from a concert, GigCrowd is being built to make every live music experience easier to discover, remember, and share.

---

## ✨ Features

### 🎫 Concert Discovery

Search for artists and explore live events through integrated music and event data providers.

### 🎵 Artist Discovery and Profiles

Find artists, explore their information, and import artist data into GigCrowd.

### ❤️ Favorite Artists

Follow artists and build a personalized collection of the musicians you care about.

### 📅 Concert History

Build a personal record of live music experiences and keep track of concerts attended.

### 👥 Social Community

Connect with other music fans and discover shared interests through social features.

### 📸 Concert Memories

Share posts and photos to preserve the experiences behind each show.

### 🤖 Personalized Recommendations — Planned

Explore future recommendations based on favorite artists, music preferences, concert history, and community activity.

> Feature availability may vary while development and deployment continue.

---

## 🏗️ Architecture

GigCrowd uses a frontend/backend architecture with a REST API and a document-oriented database.

```text
                 Next.js + React
                        │
                        ▼
                   FastAPI
                  REST API
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
           MongoDB          External Providers
                                  │
                           Spotify + Songkick
```

### Project Structure

```text
GigCrowd/
├── frontend/       # Next.js application
└── backend/        # FastAPI application
```

---

## 🛠️ Tech Stack

### Frontend

* Next.js
* React
* TypeScript
* Tailwind CSS
* next-intl for internationalization

### Backend

* Python
* FastAPI
* REST API architecture
* JWT authentication
* Pytest

### Database

* MongoDB
* MongoDB Atlas for hosted database infrastructure

### Integrations

* **Spotify API** — artist discovery and artist image data.
* **Songkick** — artist resolution and concert/event data.

### Deployment

* **Vercel** — frontend hosting.
* **Render** — backend hosting.
* **MongoDB Atlas** — managed database.

### Development Tools

* Git and GitHub
* Docker for containerized development and infrastructure
* Playwright for browser automation and testing where applicable

> RabbitMQ and other infrastructure components may be introduced as the project evolves.

---

## 🗺️ Roadmap

### Implemented foundations

* JWT authentication foundation.
* User and artist API foundations.
* Artist search and import workflow.
* Spotify artist discovery integration.
* Songkick artist resolution and event data integration.
* Follow system foundation.
* REST API structure.
* Frontend and backend deployment.

### In development

* Artist and event experience improvements.
* Activity feed and community interactions.
* Concert attendance tracking.
* Social posts and media uploads.
* Event timeline.
* Data enrichment and search improvements.

### Planned

* Personalized recommendations.
* Festival and lineup exploration.
* Concert wishlist.
* Expanded notifications.
* Further mobile experience improvements.
* Additional automation and infrastructure integrations.

---

## 🧪 Development and Testing

To run GigCrowd locally, you will need Python, Node.js, and access to a MongoDB instance.

### Backend

```bash
cd backend

python -m venv .venv
```

Activate the virtual environment and install the dependencies:

```bash
# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Configure the required environment variables using your local environment configuration. Do not commit credentials or secret values.

Start the API:

```bash
uvicorn app.main:app --reload
```

The backend will normally be available at `http://localhost:8000`.

* Swagger: `http://localhost:8000/docs`
* ReDoc: `http://localhost:8000/redoc`
* Health check: `http://localhost:8000/health`

### Frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Configure `NEXT_PUBLIC_API_URL` to point to the backend URL being used. For local development, this is typically `http://localhost:8000`.

The frontend will normally be available at `http://localhost:3000`.

> Consult the project configuration and environment variables for any additional integration credentials or setup requirements.

---

## 🔐 Security

* Authentication is handled through JWT-based mechanisms.
* Secrets and API credentials should be configured through environment variables.
* Production and development environments should use separate configuration.
* Never commit `.env` files containing real credentials.
* Public API documentation does not mean every endpoint is publicly accessible; some routes require authentication.

---

## ❤️ Why GigCrowd?

GigCrowd started with a simple frustration: there was no single place dedicated to the complete concert experience.

Discovering a show, finding other fans, tracking attendance, and remembering the moments that made a concert special are experiences worth connecting.

GigCrowd is a personal project inspired by the relationship between music, live experiences, memories, and community.

The goal is not simply to list concerts, but to build a place where every show can become part of someone's story.

---

## 🤝 Contributing

Ideas, feedback, and bug reports are welcome.

If you'd like to contribute:

1. Fork the repository.
2. Create a feature branch.
3. Make your changes and run the relevant tests.
4. Open a Pull Request describing the changes.

For bugs or suggestions, open an issue with enough detail to reproduce the problem or explain the proposed improvement.

---

## 🔮 Vision

GigCrowd aims to become a home for live music enthusiasts: a place to discover concerts, follow artists, document experiences, preserve memories, and connect with people who love live music.

Because every concert tells a story.

**GigCrowd is where those stories live.**

---

<p align="center">

Made with ❤️ by **Leticia Cruz**

</p>
