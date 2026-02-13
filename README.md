# Media Manager

A self-hosted web application for managing media requests against a Jellyfin server. Users browse and search for movies/TV shows via TMDB, submit requests, and admins manage the request pipeline.

## Prerequisites

- Python 3.11+
- Node.js 20+
- A running [Jellyfin](https://jellyfin.org/) server
- A [TMDB API key](https://www.themoviedb.org/settings/api) (free)

## Getting Started

### 1. Clone the repo

```bash
git clone <repo-url>
cd mediamanager
```

### 2. Backend setup

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Create a `backend/.env` file with your configuration:

```env
JELLYFIN_URL=http://localhost:8096
TMDB_API_KEY=your-tmdb-api-key
SECRET_KEY=some-random-secret-string
```

Start the backend:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3. Frontend setup

In a separate terminal:

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev -- --host 0.0.0.0
```

### 4. Open the app

Go to **http://localhost:5173** in your browser and log in with your Jellyfin credentials.

## Configuration

All backend config is via environment variables in `backend/.env`:

| Variable | Default | Description |
|---|---|---|
| `JELLYFIN_URL` | `http://localhost:8096` | Your Jellyfin server URL |
| `TMDB_API_KEY` | *(required)* | TMDB v3 API key |
| `SECRET_KEY` | `change-me` | Random string for JWT signing |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `NGROK_AUTHTOKEN` | *(optional)* | ngrok auth token for remote access |
| `NGROK_DOMAIN` | *(optional)* | Custom ngrok domain |

## Tech Stack

- **Backend**: Python / FastAPI
- **Frontend**: React / TypeScript / Tailwind CSS (Vite)
- **Database**: SQLite
- **Auth**: Jellyfin user accounts (proxied authentication)
- **Media Data**: TMDB API

## Remote Access (optional)

To expose the app publicly via ngrok:

```bash
ngrok http 5173 --domain your-domain.ngrok.app
```

Or start/stop the tunnel from the Admin panel's Tunnel tab.

A cron-based health check script is included to keep services alive:

```
*/10 * * * * /path/to/mediamanager/scripts/healthcheck.sh
```
