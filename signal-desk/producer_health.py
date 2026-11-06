"""Small JSON health/observation sidecars; no database schema changes."""
import datetime as dt
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def finish(producer, errors, *, path=None, no_games=False):
    data = {"producer": producer, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "status": "degraded" if errors else ("no_games" if no_games else "ok"), "errors": errors}
    write(path or DATA / "producer_health" / f"{producer}.json", data)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)


def record_checks(observations, now, path=None):
    path = Path(path or DATA / "source_heartbeats.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {"records": {}}
    for record_id, event_id, changed in observations:
        previous = data["records"].get(record_id, {})
        data["records"][record_id] = {
            "source": "ESPN", "event_id": event_id, "checked_at": now,
            "changed_at": now if changed else previous.get("changed_at"),
        }
    data["generated_at"] = now
    write(path, data)
