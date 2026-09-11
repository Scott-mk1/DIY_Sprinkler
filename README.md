# Irrigation Service

A small self-hosted service that schedules WebRelay-controlled sprinkler
valves and skips watering automatically when rain is likely. Everything is
configured from the web UI — no editing config files or code.

## What it does

- **Dashboard** (`/`) — a compact grid of zone tiles, Wyze-style: photo
  thumbnail, name, on/off toggle, and a quick-run button. Tap a tile to open
  it.
- **Zone page** (`/zones/<id>`) — photo upload, water-now controls, the
  zone's schedule, and its edit/delete controls.
- **Settings page** (`/settings`) — add new zones, weather/location config,
  and the activity log. Kept off the dashboard so the front page stays
  simple.
- Rain check via Open-Meteo before every scheduled run — skips and logs it
  if the forecast is at/above your threshold.
- Dark mode — toggle in the header, remembered in your browser.
- Photo per zone — upload from the zone page; shows as the tile thumbnail
  on the dashboard so it's obvious which zone is which at a glance.

## Hardware assumption

Built around the ControlByWeb WebRelay-10 (and compatible WebRelay/Quad
units), which expose a plain HTTP API:

    GET http://<relay-ip>/state.xml?relay<N>State=1   # on
    GET http://<relay-ip>/state.xml?relay<N>State=0   # off

If you end up spreading 9+ zones across two WebRelay-10 units, that's fine —
each zone just stores its own relay host IP, so zones can point at different
units. Channel numbers are per-unit (1-10), not global.

If your WebRelay units have HTTP auth turned on, set these in
`docker-compose.yml` before starting (same credentials for all units):

    environment:
      - RELAY_USERNAME=admin
      - RELAY_PASSWORD=webrelay

## Running it (ZimaOS / any Docker host)

1. Copy this whole folder to your homelab (e.g. via `scp` or the ZimaOS file
   manager).
2. Edit `docker-compose.yml` — set your timezone (`TZ`) and, if needed,
   `RELAY_USERNAME` / `RELAY_PASSWORD`.
3. From the folder:

       docker compose up -d --build

   Runs on host port 8088 (8000 is already taken by Paperless-NGX on this
   box). Change the host-side number in `docker-compose.yml` if 8088 ever
   collides with something else — the container's internal port stays 8000
   either way.

4. Open `http://<your-server-ip>:8088` from your phone or any browser on
   your network.

Data (zones, schedules, log) lives in SQLite at `./data/sprinkler.db` on the
host via the mounted volume, so it survives container rebuilds/restarts.

## First-time setup in the UI

1. Open **Settings** (gear icon) and confirm latitude/longitude (defaults to
   Cheshire, CT) and your rain-skip threshold.
2. Still in Settings, add each of your 9+ zones — name, relay IP, channel
   number.
3. Back on the dashboard, tap into a zone and upload a photo of it — makes
   the grid much faster to scan once you're past 4-5 zones.
4. From each zone's page, add its schedule — days, start time, duration.
5. Use **Water now** (or the quick-run button on the dashboard tile) any
   time to test a zone's wiring without waiting for its schedule.

## Notes on the rain check

- If Open-Meteo can't be reached when a schedule fires, the run proceeds
  anyway (fails open) rather than silently skip watering — a missed
  forecast check shouldn't mean a dead lawn. This is logged as an error so
  you can see if it's happening often.
- The threshold compares against Open-Meteo's daily max precipitation
  probability for today, refreshed on every schedule trigger — not a
  cached value from setup time.

## Files

- `main.py` — FastAPI routes for all three pages, plus photo upload
- `scheduler.py` — APScheduler jobs, weather-gated start/stop logic
- `relay.py` — WebRelay HTTP control
- `weather.py` — Open-Meteo rain check
- `db.py` — SQLite schema/helpers (includes the zone photo column)
- `templates/base.html` — shared header/theme scaffolding
- `templates/index.html` — dashboard grid
- `templates/zone_detail.html` — per-zone page (photo, water-now, schedule, edit)
- `templates/settings.html` — add-zone, weather config, activity log
- `static/` — stylesheet (light + dark tokens) and the theme-toggle script

Zone photos are stored on disk next to the database (`./data/photos/` by
default) and referenced by filename in SQLite — they ride along with the
rest of your data in the mounted volume, so they survive rebuilds too.
