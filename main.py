import os
from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

import db
import weather
import scheduler as sched_mod

PHOTOS_DIR = os.path.join(os.path.dirname(os.path.abspath(db.DB_PATH)), "photos")
ALLOWED_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    sched_mod.start_scheduler()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
os.makedirs(PHOTOS_DIR, exist_ok=True)
app.mount("/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")
templates = Jinja2Templates(directory="templates")


def _zone_with_status(z: dict) -> dict:
    z["running"] = z["id"] in sched_mod.active_runs
    z["stop_time"] = sched_mod.active_runs.get(z["id"], {}).get("stop_time")
    return z


# ---------- Dashboard (compact grid) ----------

@app.get("/")
def index(request: Request):
    with db.get_conn() as conn:
        zones = db.rows_to_dicts(conn.execute("SELECT * FROM zones ORDER BY sort_order, id").fetchall())
    for z in zones:
        _zone_with_status(z)

    settings = sched_mod.get_settings()
    forecast = weather.get_rain_forecast(float(settings["latitude"]), float(settings["longitude"]))
    running_count = sum(1 for z in zones if z["running"])

    return templates.TemplateResponse(request, "index.html", {
        "zones": zones, "settings": settings, "forecast": forecast,
        "running_count": running_count,
    })


# ---------- Zone detail page ----------

@app.get("/zones/{zone_id}")
def zone_detail(request: Request, zone_id: int):
    with db.get_conn() as conn:
        zone = conn.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)).fetchone()
        if zone is None:
            raise HTTPException(404)
        zone = dict(zone)
        zone["schedules"] = db.rows_to_dicts(
            conn.execute("SELECT * FROM schedules WHERE zone_id = ? ORDER BY start_time", (zone_id,)).fetchall()
        )
    _zone_with_status(zone)
    return templates.TemplateResponse(request, "zone_detail.html", {"zone": zone})


@app.post("/zones/{zone_id}/photo")
async def upload_zone_photo(zone_id: int, photo: UploadFile = File(...)):
    ext = os.path.splitext(photo.filename or "")[1].lower()
    if ext not in ALLOWED_PHOTO_EXTS:
        raise HTTPException(400, "Unsupported image type — use jpg, png, or webp.")
    filename = f"zone-{zone_id}{ext}"
    dest = os.path.join(PHOTOS_DIR, filename)
    content = await photo.read()
    with open(dest, "wb") as f:
        f.write(content)
    with db.get_conn() as conn:
        conn.execute("UPDATE zones SET photo_filename = ? WHERE id = ?", (filename, zone_id))
        conn.commit()
    return RedirectResponse(f"/zones/{zone_id}", status_code=303)


# ---------- Zones ----------

@app.post("/zones/add")
def add_zone(name: str = Form(...), relay_host: str = Form(...), relay_channel: int = Form(...)):
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO zones (name, relay_host, relay_channel) VALUES (?, ?, ?)",
            (name.strip(), relay_host.strip(), relay_channel),
        )
        conn.commit()
    return RedirectResponse("/settings", status_code=303)


@app.post("/zones/{zone_id}/edit")
def edit_zone(zone_id: int, name: str = Form(...), relay_host: str = Form(...),
              relay_channel: int = Form(...), enabled: str = Form(None)):
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE zones SET name = ?, relay_host = ?, relay_channel = ?, enabled = ? WHERE id = ?",
            (name.strip(), relay_host.strip(), relay_channel, 1 if enabled else 0, zone_id),
        )
        conn.commit()
    return RedirectResponse(f"/zones/{zone_id}", status_code=303)


@app.post("/zones/{zone_id}/toggle_enabled")
def toggle_zone_enabled(zone_id: int, redirect_to: str = Form("/")):
    with db.get_conn() as conn:
        row = conn.execute("SELECT enabled FROM zones WHERE id = ?", (zone_id,)).fetchone()
        if row is None:
            raise HTTPException(404)
        conn.execute("UPDATE zones SET enabled = ? WHERE id = ?", (0 if row["enabled"] else 1, zone_id))
        conn.commit()
    sched_mod.reload_all_schedules()
    return RedirectResponse(redirect_to, status_code=303)


@app.post("/zones/{zone_id}/delete")
def delete_zone(zone_id: int):
    with db.get_conn() as conn:
        row = conn.execute("SELECT photo_filename FROM zones WHERE id = ?", (zone_id,)).fetchone()
        conn.execute("DELETE FROM zones WHERE id = ?", (zone_id,))
        conn.commit()
    if row and row["photo_filename"]:
        try:
            os.remove(os.path.join(PHOTOS_DIR, row["photo_filename"]))
        except OSError:
            pass
    sched_mod.reload_all_schedules()
    return RedirectResponse("/", status_code=303)


# ---------- Schedules ----------

@app.post("/zones/{zone_id}/schedules/add")
def add_schedule(zone_id: int, days_of_week: list[str] = Form(...),
                  start_time: str = Form(...), duration_minutes: int = Form(...)):
    days = ",".join(days_of_week)
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO schedules (zone_id, days_of_week, start_time, duration_minutes) "
            "VALUES (?, ?, ?, ?)",
            (zone_id, days, start_time, duration_minutes),
        )
        conn.commit()
    sched_mod.reload_all_schedules()
    return RedirectResponse(f"/zones/{zone_id}", status_code=303)


@app.post("/schedules/{schedule_id}/delete")
def delete_schedule(schedule_id: int):
    with db.get_conn() as conn:
        row = conn.execute("SELECT zone_id FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        conn.commit()
    sched_mod.reload_all_schedules()
    zone_id = row["zone_id"] if row else None
    return RedirectResponse(f"/zones/{zone_id}" if zone_id else "/", status_code=303)


@app.post("/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int):
    with db.get_conn() as conn:
        row = conn.execute("SELECT enabled, zone_id FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        if row is None:
            raise HTTPException(404)
        conn.execute("UPDATE schedules SET enabled = ? WHERE id = ?", (0 if row["enabled"] else 1, schedule_id))
        conn.commit()
    sched_mod.reload_all_schedules()
    return RedirectResponse(f"/zones/{row['zone_id']}", status_code=303)


# ---------- Manual control ----------

@app.post("/zones/{zone_id}/water_now")
def water_now(zone_id: int, duration_minutes: int = Form(10), bypass_weather: str = Form(None),
              redirect_to: str = Form("/")):
    with db.get_conn() as conn:
        zone = conn.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)).fetchone()
    if zone is None:
        raise HTTPException(404)
    sched_mod.start_zone(dict(zone), duration_minutes=duration_minutes, bypass_weather=bool(bypass_weather))
    return RedirectResponse(redirect_to, status_code=303)


@app.post("/zones/{zone_id}/stop_now")
def stop_now(zone_id: int, redirect_to: str = Form("/")):
    sched_mod.stop_zone(zone_id, manual=True)
    return RedirectResponse(redirect_to, status_code=303)


@app.post("/stop_all")
def stop_all(redirect_to: str = Form("/")):
    for zone_id in list(sched_mod.active_runs.keys()):
        sched_mod.stop_zone(zone_id, manual=True)
    return RedirectResponse(redirect_to, status_code=303)


# ---------- Settings page ----------

@app.get("/settings")
def settings_page(request: Request):
    settings = sched_mod.get_settings()
    with db.get_conn() as conn:
        log_rows = db.rows_to_dicts(
            conn.execute("SELECT * FROM run_log ORDER BY id DESC LIMIT 40").fetchall()
        )
    return templates.TemplateResponse(request, "settings.html", {
        "settings": settings, "log_rows": log_rows,
    })


@app.post("/settings/update")
def update_settings(latitude: str = Form(...), longitude: str = Form(...),
                     rain_check_enabled: str = Form(None), rain_skip_threshold: int = Form(...)):
    with db.get_conn() as conn:
        conn.execute("UPDATE settings SET value = ? WHERE key = 'latitude'", (latitude,))
        conn.execute("UPDATE settings SET value = ? WHERE key = 'longitude'", (longitude,))
        conn.execute("UPDATE settings SET value = ? WHERE key = 'rain_check_enabled'",
                     ("1" if rain_check_enabled else "0",))
        conn.execute("UPDATE settings SET value = ? WHERE key = 'rain_skip_threshold'",
                     (str(rain_skip_threshold),))
        conn.commit()
    return RedirectResponse("/settings", status_code=303)


# ---------- JSON status ----------

@app.get("/api/status")
def api_status():
    settings = sched_mod.get_settings()
    forecast = weather.get_rain_forecast(float(settings["latitude"]), float(settings["longitude"]))
    with db.get_conn() as conn:
        zones = db.rows_to_dicts(conn.execute("SELECT * FROM zones").fetchall())
    for z in zones:
        z["running"] = z["id"] in sched_mod.active_runs
    return {"zones": zones, "forecast": forecast, "active_runs": sched_mod.active_runs}
