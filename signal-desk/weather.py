"""Game-time weather from Open-Meteo (free, no key) and its prior effect on the spread.

Weather compresses margins: bad conditions shrink the favourite's edge toward zero (fewer big plays,
fewer points). The prior is deliberately small and is a PRIOR ASSUMPTION; calibrate.py learns one
scale for it from graded games (Factor Scale Weather) like every other factor.

Pure parsing and scoring are separate from the fetch so they can be unit-tested offline.
Forecasts only exist ~7 days ahead; farther games get no weather note (unknown is not clear).
"""
from __future__ import annotations

import datetime as dt
import re
import urllib.parse

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search?name={name}&count=10&countryCode=US"
FORECAST = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&hourly=temperature_2m,wind_speed_10m,precipitation_probability,snowfall,rain"
            "&wind_speed_unit=mph&temperature_unit=fahrenheit&forecast_days=7&timezone=UTC")
MAX_AHEAD_DAYS = 6.5
COMPRESS = 0.10          # prior: share of the model margin lost at severity 1.0
MAX_WEATHER_PTS = 1.5    # most the weather term can move a margin
_SEV = re.compile(r"sev=([0-9.]+)")


def severity(wind_mph: float | None, precip_prob: float | None, snow_cm: float | None, temp_f: float | None) -> float:
    """0 (benign) to 1 (severe). Takes the worst single condition, not a sum."""
    s = 0.0
    if wind_mph is not None:
        s = max(s, 1.0 if wind_mph >= 20 else 0.6 if wind_mph >= 15 else 0.25 if wind_mph >= 10 else 0.0)
    if snow_cm is not None and snow_cm >= 0.1:
        s = max(s, 0.7)
    if precip_prob is not None and precip_prob >= 60:
        s = max(s, 0.4)
    if temp_f is not None:
        s = max(s, 0.3 if temp_f <= 20 else 0.15 if temp_f <= 32 else 0.0)
    return s


def pick_hours(hourly: dict, kickoff: dt.datetime, hours: int = 3) -> dict | None:
    """Worst conditions in the `hours` after kickoff from an Open-Meteo hourly block (UTC times)."""
    times = hourly.get("time") or []
    start = kickoff.astimezone(dt.timezone.utc).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    idx = []
    for i, t in enumerate(times):
        try:
            when = dt.datetime.fromisoformat(t)
        except ValueError:
            continue
        if 0 <= (when - start).total_seconds() < hours * 3600:
            idx.append(i)
    if not idx:
        return None

    def col(name, fn):
        vals = [hourly[name][i] for i in idx if hourly.get(name) and hourly[name][i] is not None]
        return fn(vals) if vals else None
    return {"temp": col("temperature_2m", min), "wind": col("wind_speed_10m", max),
            "precip": col("precipitation_probability", max), "snow": col("snowfall", sum)}


def note(w: dict | None, indoor: bool) -> str:
    if indoor:
        return "indoor | sev=0.00"
    if not w:
        return ""
    s = severity(w["wind"], w["precip"], w["snow"], w["temp"])
    bits = []
    if w["temp"] is not None:
        bits.append(f"{w['temp']:.0f}F")
    if w["wind"] is not None:
        bits.append(f"wind {w['wind']:.0f}mph")
    if w["precip"] is not None:
        bits.append(f"precip {w['precip']:.0f}%")
    if w["snow"]:
        bits.append(f"snow {w['snow']:.1f}cm")
    return f"{', '.join(bits)} | sev={s:.2f} | open-meteo"


def sev_from_note(text: str | None) -> float | None:
    m = _SEV.search(text or "")
    return float(m.group(1)) if m else None


def weather_points(model_margin: float, sev: float | None) -> float:
    """Home-favouring points: shrink the model margin toward 0 by COMPRESS * severity."""
    if not sev:
        return 0.0
    pts = -model_margin * COMPRESS * sev
    return max(-MAX_WEATHER_PTS, min(MAX_WEATHER_PTS, pts))


def lookup(city: str, state: str, get_json, cache: dict) -> tuple[float, float] | None:
    key = (city, state)
    if key in cache:
        return cache[key]
    out = None
    try:
        res = get_json(GEOCODE.format(name=urllib.parse.quote(city))).get("results") or []
        for r in res:
            if (r.get("admin1") or "").lower() == STATE_NAMES.get(state, state).lower():
                out = (r["latitude"], r["longitude"])
                break
        if out is None and res:
            out = (res[0]["latitude"], res[0]["longitude"])
    except Exception:  # noqa: BLE001
        out = None
    cache[key] = out
    return out


def forecast_note(city: str, state: str, kickoff: dt.datetime | None, now: dt.datetime, indoor: bool,
                  get_json, geo_cache: dict, fc_cache: dict) -> str:
    """Weather note for one game, or '' when unknown. Never raises."""
    if indoor:
        return note(None, True)
    if kickoff is None or not city or not state:
        return ""
    ahead = (kickoff - now).total_seconds() / 86400
    if ahead < -0.1 or ahead > MAX_AHEAD_DAYS:
        return ""
    pos = lookup(city, state, get_json, geo_cache)
    if not pos:
        return ""
    try:
        if pos not in fc_cache:
            fc_cache[pos] = get_json(FORECAST.format(lat=pos[0], lon=pos[1])).get("hourly") or {}
        return note(pick_hours(fc_cache[pos], kickoff), False)
    except Exception:  # noqa: BLE001
        return ""


STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
