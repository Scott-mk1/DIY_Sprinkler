"""
Rain check using Open-Meteo (https://open-meteo.com) — free, no API key required.

We pull today's max precipitation probability and forecast precipitation sum.
If the probability meets/exceeds the configured threshold, watering is skipped
for that run.
"""
import requests

TIMEOUT_SECONDS = 8
BASE_URL = "https://api.open-meteo.com/v1/forecast"


def get_rain_forecast(latitude: float, longitude: float) -> dict:
    """
    Returns:
      {
        "ok": bool,
        "precipitation_probability_max": int | None,  # 0-100
        "precipitation_sum_mm": float | None,
        "error": str | None,
      }
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "precipitation_probability_max,precipitation_sum",
        "forecast_days": 1,
        "timezone": "auto",
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        prob = daily.get("precipitation_probability_max", [None])[0]
        precip = daily.get("precipitation_sum", [None])[0]
        return {
            "ok": True,
            "precipitation_probability_max": prob,
            "precipitation_sum_mm": precip,
            "error": None,
        }
    except (requests.RequestException, KeyError, IndexError, ValueError) as e:
        return {
            "ok": False,
            "precipitation_probability_max": None,
            "precipitation_sum_mm": None,
            "error": str(e),
        }


def should_skip_for_rain(latitude: float, longitude: float, threshold_pct: int) -> tuple[bool, str]:
    """
    Returns (skip: bool, reason: str).
    If the weather API can't be reached, we fail open (don't skip) so the
    schedule still runs — a missed forecast shouldn't leave the lawn dry.
    """
    forecast = get_rain_forecast(latitude, longitude)
    if not forecast["ok"]:
        return False, f"weather check failed ({forecast['error']}) — watering proceeded"

    prob = forecast["precipitation_probability_max"]
    if prob is None:
        return False, "no precipitation probability in forecast — watering proceeded"

    if prob >= threshold_pct:
        return True, f"skipped — {prob}% chance of rain today (threshold {threshold_pct}%)"

    return False, f"proceeding — {prob}% chance of rain today (threshold {threshold_pct}%)"
