# Media Manager

A self-hosted web application for managing media requests against a Jellyfin server. Users browse and search for movies/TV shows via TMDB, submit requests, and admins manage the request pipeline.

## Tech Stack

- **Backend**: Python / FastAPI
- **Frontend**: React / TypeScript / Tailwind CSS (Vite)
- **Database**: SQLite
- **Auth**: Jellyfin user accounts (proxied authentication)
- **Media Data**: TMDB API (The Movie Database)
- **Media Server**: Jellyfin API
- **Tunnel**: ngrok (custom domain support)

## Architecture

```
frontend (React, port 5173)
    ↓ /api proxy
backend (FastAPI, port 8000)
    ↓                ↓                ↓
Jellyfin API     TMDB API        SQLite DB
(library/auth)   (search/meta)   (requests/roles/backlog)
    ↑
ngrok tunnel (https://mediamanager.ngrok.app)
    → forwards to frontend on port 5173
```

## Features

### Authentication
- Users log in with their Jellyfin credentials
- Backend proxies auth to Jellyfin's `/Users/AuthenticateByName`
- JWT session tokens encode user info + Jellyfin access token
- Jellyfin admins automatically get app admin access
- Expired Jellyfin sessions trigger auto-redirect to login

### Search & Discovery
- Debounced search against TMDB (movies and TV shows)
- Full detail pages with poster, backdrop, cast, genres, ratings
- Search results cross-referenced with Jellyfin library — items already in the library show an "In Library" badge
- Existing request status shown on search results and detail pages

### Request System
- Users request movies/TV shows from the detail page
- Duplicate prevention (one active request per user per title)
- Users can view and cancel their pending requests from "My Requests"
- "New Request" button on My Requests page links to search

### Admin Panel
- **Requests Tab**
  - **Board View**: Kanban-style columns (Pending → Approved → Fulfilled / Denied)
  - **Table View**: Full list with inline status actions
  - Each status transition can include an optional admin note
  - Requests can be moved forwards or backwards through the pipeline
  - Stats overview: total, pending, approved, fulfilled, unique users
- **Backlog Tab**
  - Kanban board for bugs and feature requests
  - Statuses: Reported → Triaged → In Progress → Ready for Test → Resolved / Won't Fix
  - Priority levels: low, medium, high, critical (inline toggle)
  - Admin notes on status transitions
  - Delete items from any column
- **Users Tab**
  - View all users who have logged in
  - Promote/demote users between admin and user roles
  - Self-protection: admins cannot remove their own access
- **Tunnel Tab**
  - Start/stop ngrok tunnel from the UI
  - Shows public URL with copy button
  - Supports custom ngrok domains
- **Health Tab**
  - Real-time status of Jellyfin, TMDB API, and database
  - Jellyfin server name and version displayed
  - Trigger Jellyfin library rescan from the UI
  - Auto-refreshes every 30 seconds

### Backlog & Bug Reporting
- All users can report bugs or request features via "Report Issue" page
- Submissions appear in the admin Backlog tab for triage
- Users can track the status of their own submissions

### User Permissions
- `user_roles` table tracks app-level roles (`user` or `admin`)
- Admins can promote/demote users via the Users tab
- Jellyfin admin status is always respected (can't be demoted in-app)
- Admins cannot remove their own admin access

### Auto-Fulfillment
- Background task runs every 5 minutes
- Checks all pending/approved requests against the Jellyfin library
- Matches by TMDB provider ID for accuracy
- Automatically marks matching requests as "fulfilled"

### Jellyfin Library
- Browse movies and TV shows currently in the library
- Search within library content
- Library stats on the dashboard (movies, shows, episodes)
- Recently added items displayed on dashboard
- Admin can trigger library rescan from Health tab

### Mobile Responsive
- Hamburger menu with slide-out drawer on mobile
- Card-based layouts replace tables on small screens
- All pages optimized for touch and narrow viewports

### ngrok Tunnel
- Expose the app to the internet via ngrok
- Custom domain support (e.g. `mediamanager.ngrok.app`)
- Start/stop from admin panel or run standalone
- Health check cron job restarts tunnel if it goes down

## Project Structure

```
backend/
  app/
    main.py              # FastAPI app, CORS, lifespan, background tasks
    config.py            # pydantic-settings from .env
    database.py          # SQLite setup + migrations
    dependencies.py      # Auth middleware (get_current_user, require_admin)
    schemas.py           # Pydantic request/response models
    routers/
      auth.py            # Login, logout, session check
      tmdb.py            # TMDB search/detail with library cross-ref
      requests.py        # User request CRUD
      admin.py           # Admin request mgmt, user roles, health, Jellyfin scan
      jellyfin.py        # Library browsing, stats, recent items
      backlog.py         # Bug/feature reporting and admin backlog management
      tunnel.py          # ngrok tunnel start/stop/status
    services/
      jellyfin_client.py # Jellyfin API client
      tmdb_client.py     # TMDB API client
      request_service.py # Request business logic + auto-fulfill

frontend/
  src/
    api/                 # Axios client + API modules (auth, tmdb, requests, jellyfin, backlog, tunnel)
    context/             # AuthContext (login state, user info)
    hooks/               # useDebounce
    components/          # Layout, MediaCard, MediaGrid, RequestBadge, SearchBar, etc.
    pages/               # Login, Dashboard, Search, MediaDetail, Library, MyRequests, Report, Admin

scripts/
  healthcheck.sh         # Cron script to keep backend, frontend, and ngrok alive
```

## Configuration

Backend environment variables (`backend/.env`):

| Variable | Description |
|----------|-------------|
| `JELLYFIN_URL` | Jellyfin server URL (e.g. `http://192.168.1.105:8096`) |
| `TMDB_API_KEY` | TMDB v3 API key (free at themoviedb.org) |
| `SECRET_KEY` | Random string for JWT signing |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `NGROK_AUTHTOKEN` | ngrok auth token (from ngrok.com) |
| `NGROK_DOMAIN` | Custom ngrok domain (e.g. `mediamanager.ngrok.app`) |

## Running

**Backend:**
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npx vite --host 0.0.0.0
```

**ngrok Tunnel:**
```bash
ngrok http 5173 --domain mediamanager.ngrok.app
```

**Cron Health Check** (runs every 10 minutes):
```
*/10 * * * * /home/neehawranch/Projects/mediamanager/scripts/healthcheck.sh
```

### Access
- Local: `http://localhost:5173`
- Network: `http://<your-ip>:5173`
- Public: `https://mediamanager.ngrok.app`
