"""
Controls ControlByWeb WebRelay-10 (and compatible WebRelay/WebRelay-Quad) units
over their built-in HTTP API.

Command format:
  GET http://<relay-ip>/state.xml?relay<N>State=<0|1|2>
    0 = off, 1 = on, 2 = pulse

If your unit has HTTP auth enabled (default user is usually "admin"),
set RELAY_USERNAME / RELAY_PASSWORD env vars and they'll be used for all units.
"""
import os
import requests

RELAY_USERNAME = os.environ.get("RELAY_USERNAME", "")
RELAY_PASSWORD = os.environ.get("RELAY_PASSWORD", "")
TIMEOUT_SECONDS = 5


def _auth():
    if RELAY_USERNAME or RELAY_PASSWORD:
        return (RELAY_USERNAME, RELAY_PASSWORD)
    return None


def set_relay(host: str, channel: int, on: bool) -> tuple[bool, str]:
    """Turn a relay channel on or off. Returns (success, message)."""
    state = 1 if on else 0
    url = f"http://{host}/state.xml"
    params = {f"relay{channel}State": state}
    try:
        resp = requests.get(url, params=params, auth=_auth(), timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        return True, "ok"
    except requests.RequestException as e:
        return False, str(e)


def get_status(host: str) -> tuple[bool, str]:
    """Fetch the raw state.xml for a relay host (used for a basic health check)."""
    url = f"http://{host}/state.xml"
    try:
        resp = requests.get(url, auth=_auth(), timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        return True, resp.text
    except requests.RequestException as e:
        return False, str(e)
