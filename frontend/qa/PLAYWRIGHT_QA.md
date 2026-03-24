# Playwright Smoke QA (MediaManager Frontend)

This is a lightweight first-pass smoke setup for the frontend.

## What it covers

- Login page renders and accepts user input controls
- Protected routes redirect unauthenticated users to `/login`
- Core post-login shell works (dashboard + navigation to Search/Library) using mocked API responses

## Prereqs

From `frontend/`:

```bash
npm install
npx playwright install chromium
```

## Run smoke tests

```bash
npm run qa:smoke
```

Headed mode:

```bash
npm run qa:smoke:headed
```

## Run as parallel missions (for `playwright-parallel-qa` skill)

`qa/missions.tsv` contains mission commands.

From `frontend/`:

```bash
npm run qa:missions
```

Or manually with a custom output dir:

```bash
python3 ../../skills/playwright-parallel-qa/scripts/run_missions.py \
  --missions qa/missions.tsv \
  --out artifacts/playwright-qa/$(date +%Y-%m-%d_%H-%M-%S) \
  --max-parallel 3
```

## Notes

- Tests default to local URL `http://127.0.0.1:4173` via Playwright `webServer`.
- If your dev server uses a different port:

```bash
PW_PORT=5173 PW_BASE_URL=http://127.0.0.1:5173 npm run qa:smoke
```

- Assertions use visible labels/text and nav link names; if UI copy changes, update selectors accordingly.
