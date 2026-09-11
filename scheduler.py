import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

import db
import relay
import weather

DOW_MAP = {"mon": "mon", "tue": "tue", "wed": "wed", "thu": "thu",
           "fri": "fri", "sat": "sat", "sun": "sun"}

scheduler = BackgroundScheduler()

# tracks currently-running zones: {zone_id: {"job_id": stop_job_id, "schedule_id": ...}}
active_runs: dict[int, dict] = {}


def log_event(zone_id, zone_name, schedule_id, action, detail=""):
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO run_log (zone_id, zone_name, schedule_id, event_time, action, detail) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (zone_id, zone_name, schedule_id, datetime.datetime.now().isoformat(timespec="seconds"),
             action, detail),
        )
        conn.commit()


def get_settings() -> dict:
    with db.get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def start_zone(zone: dict, schedule_id=None, duration_minutes=None, bypass_weather=False):
    """Turns a zone's relay on, checking weather first unless bypassed. Schedules auto-stop."""
    zone_id = zone["id"]

    if zone_id in active_runs:
        return False, "zone already running"

    settings = get_settings()
    if not bypass_weather and settings.get("rain_check_enabled") == "1":
        skip, reason = weather.should_skip_for_rain(
            float(settings["latitude"]), float(settings["longitude"]),
            int(settings["rain_skip_threshold"]),
        )
        if skip:
            log_event(zone_id, zone["name"], schedule_id, "skipped_rain", reason)
            return False, reason

    ok, msg = relay.set_relay(zone["relay_host"], zone["relay_channel"], True)
    if not ok:
        log_event(zone_id, zone["name"], schedule_id, "error", f"failed to turn on: {msg}")
        return False, f"relay error: {msg}"

    action = "manual_start" if schedule_id is None else "started"
    log_event(zone_id, zone["name"], schedule_id, action)

    run_minutes = duration_minutes if duration_minutes is not None else 10
    stop_time = datetime.datetime.now() + datetime.timedelta(minutes=run_minutes)
    job = scheduler.add_job(
        stop_zone, trigger=DateTrigger(run_date=stop_time),
        args=[zone_id, schedule_id], id=f"stop-zone-{zone_id}-{stop_time.timestamp()}",
    )
    active_runs[zone_id] = {"job_id": job.id, "schedule_id": schedule_id, "stop_time": stop_time.isoformat()}
    return True, "started"


def stop_zone(zone_id: int, schedule_id=None, manual=False):
    with db.get_conn() as conn:
        zone = conn.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)).fetchone()
    if zone is None:
        active_runs.pop(zone_id, None)
        return False, "zone not found"

    ok, msg = relay.set_relay(zone["relay_host"], zone["relay_channel"], False)
    action = "manual_stop" if manual else "stopped"
    log_event(zone_id, zone["name"], schedule_id, action, "" if ok else f"relay error on stop: {msg}")

    run_info = active_runs.pop(zone_id, None)
    if run_info and not manual:
        pass  # job already firing, nothing to cancel
    elif run_info and manual:
        try:
            scheduler.remove_job(run_info["job_id"])
        except Exception:
            pass
    return ok, msg


def _schedule_trigger_fn(schedule_id: int):
    """Called by APScheduler when a schedule's start time hits."""
    with db.get_conn() as conn:
        sched = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        if sched is None or not sched["enabled"]:
            return
        zone = conn.execute("SELECT * FROM zones WHERE id = ?", (sched["zone_id"],)).fetchone()
        if zone is None or not zone["enabled"]:
            return
    start_zone(dict(zone), schedule_id=schedule_id, duration_minutes=sched["duration_minutes"])


def reload_all_schedules():
    """Clears and re-adds all cron jobs from the DB. Call after any schedule edit."""
    for job in scheduler.get_jobs():
        if job.id.startswith("sched-"):
            scheduler.remove_job(job.id)

    with db.get_conn() as conn:
        schedules = conn.execute("SELECT * FROM schedules WHERE enabled = 1").fetchall()

    for sched in schedules:
        days = sched["days_of_week"]  # e.g. "mon,wed,fri"
        hour, minute = sched["start_time"].split(":")
        scheduler.add_job(
            _schedule_trigger_fn,
            trigger=CronTrigger(day_of_week=days, hour=int(hour), minute=int(minute)),
            args=[sched["id"]],
            id=f"sched-{sched['id']}",
            replace_existing=True,
        )


def start_scheduler():
    db.init_db()
    reload_all_schedules()
    scheduler.start()
