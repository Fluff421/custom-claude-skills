#!/usr/bin/env python3
"""Signal Desk ops export: machine-readable health + graded-pick data for the repo.

Writes two files that Grok/Claude/humans can read on GitHub without Airtable access
or unzipping Actions logs:

  signal-desk/data/graded_picks.csv   one row per graded pick (inputs, pick, close, result)
  signal-desk/data/ops_status.json    (a) row-level Ledger health from Airtable and
                                      (b) per-workflow run health parsed from the
                                          job logs of recent scheduled/manual runs

A workflow run with conclusion "success" is NOT treated as healthy: the scripts print
warnings (HTTP 402/403, unmatched games, missing FPI) and still exit 0, so this export
reads the log text and reports what it finds. If a log cannot be read the run is marked
"unknown", never "ok".

Read-only against Airtable and GitHub. Never writes Splash fields. Never prints secrets.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import espn_sync as es

LEDGER = "tbl3tFHFhvyNMpksE"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CENTRAL = ZoneInfo("America/Chicago")
WORKFLOWS = {  # workflow file -> label
    "espn-sync.yml": "ESPN Sync",
    "picks.yml": "Pick Engine",
    "close-grade.yml": "Close & Grade",
    "injury-pull.yml": "NCAAF Injury Pull",
    "context-calibrate.yml": "Context & Calibrate",
    "snapshot.yml": "Snapshot",
    "grade-bim-board.yml": "BIM Grader",
}
# Scheduled-run expectations. GitHub drops or delays cron runs under load (seen Oct 30: ESPN Sync,
# Snapshot and Calibrate scheduled runs never fired), so a success conclusion on old runs is not
# proof the schedule is alive. max_gap_h is the longest quiet period tolerated before "missed".
SCHEDULE_EXPECT = {
    "espn-sync.yml": ("ESPN Sync", 3, 4),
    "picks.yml": ("Pick Engine", 3, 4),
    "close-grade.yml": ("Close & Grade", 1, 2),
    "context-calibrate.yml": ("Context & Calibrate", 24, 26),
    "snapshot.yml": ("Snapshot", 24, 26),
    "grade-bim-board.yml": ("BIM Grader", 2, 6),  # Sun, Mon, Thu, Fri, Sat only; see schedule_health()
    "injury-pull.yml": ("NCAAF Injury Pull", 3, 4),  # Wed-Sat; Sun-Tue is daily, see schedule_health()
}
LOOKBACK_HOURS = 36
RUNS_PER_WORKFLOW = 4
SPLASH_GAP_FLAG = 3.0  # market-comparison review signal, never automatic proof of bad data
STALE_HOURS = 4
LEAN_THRESHOLD = 1.0
CAP = 25  # max game names listed per category

PICK_COLUMNS = [
    "Date", "League", "ESPN Event ID", "Game", "Home Team", "Away Team", "Neutral Site",
    "Home FPI", "Away FPI", "HFA", "Model Home Margin", "Vegas Implied Home Margin", "Edge",
    "Sharp-Sheet Tier", "Recommended Side", "Sharp-Sheet Est. Win Prob %",
    "Sharp-Sheet Suggested Units", "Sharp-Sheet Sportsbook", "Closing Spread (Home)",
    "Sharp-Sheet Closing Line", "Sharp-Sheet CLV Points", "Home Score", "Away Score",
    "Spread Result", "O/U Result", "Grade", "Sharp-Sheet Data Completeness",
]


# ---------- Airtable ----------
def fetch(base: str, token: str, formula: str) -> list[dict]:
    out, offset = [], None
    while True:
        url = (f"https://api.airtable.com/v0/{base}/{LEDGER}?pageSize=100&filterByFormula="
               + urllib.parse.quote(formula))
        if offset:
            url += "&offset=" + urllib.parse.quote(offset, safe="")
        page = json.loads(es.http_get(url, es.at_headers(token)))
        out.extend(page.get("records", []))
        offset = page.get("offset")
        if not offset:
            return out


def write_graded_csv(rows: list[dict]) -> int:
    rows = sorted(rows, key=lambda r: (r["fields"].get("Date", ""), r["fields"].get("Game", "")))
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "graded_picks.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(PICK_COLUMNS)
        for r in rows:
            f = r["fields"]
            w.writerow(["" if f.get(c) is None else (str(f[c]).replace("\n", " ") if not isinstance(f[c], bool)
                                                       else str(f[c]).lower()) for c in PICK_COLUMNS])
    return len(rows)


def row_health(rows: list[dict], today: dt.date, now: dt.datetime, heartbeats=None) -> dict:
    """Ledger checks. Date is a date (no kickoff time), so 'past' means before today (Central)."""
    if heartbeats is None:
        try:
            with open(os.path.join(HERE, "data", "source_heartbeats.json"), encoding="utf-8") as fh:
                heartbeats = json.load(fh).get("records", {})
        except (OSError, ValueError):
            heartbeats = {}
    cats: dict[str, list[str]] = {k: [] for k in (
        "upcoming_no_espn_event_id", "upcoming_no_fpi", "upcoming_no_splash_line",
        "upcoming_no_espn_line", "upcoming_splash_vs_espn_gap", "upcoming_edge_over_lean_but_no_pick", "upcoming_espn_data_stale",
        "past_date_no_closing_line", "past_date_no_score", "past_date_scored_but_pick_ungraded")}
    upcoming = past = 0
    for r in rows:
        f = r["fields"]
        d = f.get("Date")
        if not d:
            continue
        day = dt.date.fromisoformat(d[:10])
        name = f"{f.get('Game', r['id'])} ({f.get('League', '?')}, {d[:10]})"
        if day >= today:
            upcoming += 1
            if not f.get("ESPN Event ID"):
                cats["upcoming_no_espn_event_id"].append(name)
            if f.get("Home FPI") is None or f.get("Away FPI") is None:
                cats["upcoming_no_fpi"].append(name)
            if f.get("Vegas Implied Home Margin") is None:
                cats["upcoming_no_splash_line"].append(name)
            if f.get("ESPN Spread (Home)") is None:
                cats["upcoming_no_espn_line"].append(name)
            splash, espn = f.get("Vegas Implied Home Margin"), f.get("ESPN Spread (Home)")
            if splash is not None and espn is not None:
                gap = float(splash) + float(espn)  # 0 when Splash and ESPN agree
                if abs(gap) >= SPLASH_GAP_FLAG:
                    cats["upcoming_splash_vs_espn_gap"].append(f"{name} (gap {gap:+.1f})")
            edge = f.get("Edge")
            if edge is not None and abs(float(edge)) >= LEAN_THRESHOLD and not f.get("Sharp-Sheet Tier"):
                cats["upcoming_edge_over_lean_but_no_pick"].append(name)
            pulled = f.get("ESPN Pulled At")
            beat = heartbeats.get(r["id"], {})
            if beat.get("event_id") == str(f.get("ESPN Event ID")):
                pulled = beat.get("checked_at") or pulled
            try:
                if not pulled:
                    raise ValueError("missing observation timestamp")
                age = (now - dt.datetime.fromisoformat(pulled.replace("Z", "+00:00"))).total_seconds() / 3600
                if age >= STALE_HOURS or age < -5 / 60:
                    cats["upcoming_espn_data_stale"].append(f"{name} ({age:.0f} h)")
            except (ValueError, TypeError):
                cats["upcoming_espn_data_stale"].append(f"{name} (missing/invalid checked-at)")
        else:
            past += 1
            has_score = f.get("Home Score") is not None and f.get("Away Score") is not None
            if f.get("Closing Spread (Home)") is None and f.get("ESPN Event ID"):
                cats["past_date_no_closing_line"].append(name)
            if not has_score:
                cats["past_date_no_score"].append(name)
            elif f.get("Sharp-Sheet Tier") and f.get("Grade") not in ("Win", "Loss", "Push"):
                cats["past_date_scored_but_pick_ungraded"].append(name)
    return {"games_today_or_later": upcoming, "games_before_today": past,
            "checks": {k: {"count": len(v), "games": v[:CAP]} for k, v in cats.items()},
            "note": "Date has no kickoff time; 'before today' is by Central calendar date. "
                    "Postponed/cancelled games appear under past_date_no_score. "
                    "Splash line = 'Vegas Implied Home Margin' (entered by hand, no timestamp); "
                    "upcoming_splash_vs_espn_gap flags |Splash + ESPN spread| >= 3 points for review: "
                    "movement or differently timed observations, not proof of bad data. Imported-to-locked gaps are line movement."}


# ---------- GitHub Actions ----------
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa: D401
        return None


def gh_json(path: str, token: str):
    req = urllib.request.Request(f"https://api.github.com{path}", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "signal-desk-ops"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def gh_logs_zip(repo: str, run_id: int, token: str) -> bytes:
    """Download run logs. The API answers 302 to a signed URL; follow it WITHOUT the auth header."""
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "User-Agent": "signal-desk-ops"})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(req, timeout=60)
        raise RuntimeError("expected redirect to log archive")
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 307):
            raise RuntimeError(f"HTTP {exc.code} fetching log archive URL")
        loc = exc.headers.get("Location")
    with urllib.request.urlopen(urllib.request.Request(loc, headers={"User-Agent": "signal-desk-ops"}),
                                timeout=120) as resp:
        return resp.read()


TS = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z ")
SECRET = re.compile(r"api_key|token|secret|authorization", re.I)
PATTERNS = {
    "mode": re.compile(r"^Mode: (LIVE|DRY RUN)"),
    "rows_scanned": re.compile(r"^Ledger rows scanned: (\d+)"),
    "rows_changed": re.compile(r"^Rows with changes: (\d+)"),
    "unmatched": re.compile(r"^Unmatched to ESPN: (\d+)"),
    "new_picks": re.compile(r"^New picks: (\d+)"),
    "units_recapped": re.compile(r"^Units re-capped: (\d+)"),
    "ledger_patches": re.compile(r"^Ledger patches: (\d+)"),
    "leg_patches": re.compile(r"^Leg patches: (\d+)"),
    "calibration_upserts": re.compile(r"^Calibration upserts: (\d+)"),
    "rows_updated": re.compile(r"^Rows updated: (\d+)"),
    "injury_games_expected": re.compile(r"^Replacement games expected: (\d+)"),
    "injury_games_covered": re.compile(r"^Replacement games covered: (\d+)"),
    "injury_games_not_yet_due": re.compile(r"^Replacement games with official report not yet due: (\d+)"),
    "injury_games_overdue": re.compile(r"^Replacement games with official report overdue: (\d+)"),
    "injury_games_independent": re.compile(r"^Replacement games with an independent program \(no official report\): (\d+)"),
}


def parse_log(text: str) -> dict:
    info: dict = {"warnings": [], "http_errors": {}, "error_lines": []}
    fpi_missing = 0
    for raw in text.splitlines():
        line = TS.sub("", raw.lstrip("\ufeff")).strip()
        if not line or SECRET.search(line):
            continue
        for key, pat in PATTERNS.items():
            m = pat.match(line)
            if m and key not in info:
                info[key] = m.group(1) if key == "mode" else int(m.group(1))
        if line.startswith("WARN") and not line.startswith("WARNING:"):
            if line not in info["warnings"]:
                info["warnings"].append(line[:220])
        if "FPI missing for" in line:
            fpi_missing += 1
        for code in re.findall(r"HTTP (4\d\d|5\d\d) from ([\w.\-]+)", line):
            k = f"{code[0]} {code[1]}"
            info["http_errors"][k] = info["http_errors"].get(k, 0) + 1
        if line.startswith("ERROR") or "Traceback (most recent call last)" in line:
            if len(info["error_lines"]) < 5:
                info["error_lines"].append(line[:220])
    info["fpi_missing"] = fpi_missing
    info["warnings"] = info["warnings"][:8]
    return info


def judge(label: str, conclusion: str, info: dict | None) -> tuple[str, list[str]]:
    if conclusion not in ("success",):
        return "failed", [f"conclusion={conclusion}"]
    if info is None:
        return "unknown", ["log not readable; conclusion=success is not proof of health"]
    why = []
    source_failure = label == "NCAAF Injury Pull" and any(
        re.search(r"fetch/parse failed|treated as failed|parsed only", w, re.I) for w in info["warnings"])
    if source_failure:
        why.append("required injury source unavailable or invalid")
    # Every expected game must be accounted for: a published report, or the source's own
    # labelled state (not yet due, overdue, independent program). Unexplained gaps stay severe.
    accounted = sum(info.get(k, 0) for k in ("injury_games_covered", "injury_games_not_yet_due",
                                               "injury_games_overdue", "injury_games_independent"))
    incomplete_injuries = (label == "NCAAF Injury Pull"
                           and info.get("injury_games_expected", 0) > 0
                           and accounted != info["injury_games_expected"])
    if incomplete_injuries:
        why.append("replacement injury coverage is incomplete")
    if info["error_lines"]:
        why.append("error lines in log")
    for k, n in info["http_errors"].items():
        why.append(f"HTTP {k} x{n}")
    if label == "ESPN Sync":
        if info.get("unmatched", 0) and info.get("rows_scanned") and info["unmatched"] >= info["rows_scanned"]:
            why.append(f"all {info['unmatched']} scanned games unmatched")
        elif info.get("unmatched", 0):
            why.append(f"{info['unmatched']} games unmatched")
        if info["fpi_missing"]:
            why.append(f"FPI missing for {info['fpi_missing']} games")
        if any("stale" in w.lower() for w in info["warnings"]):
            why.append("stale FPI warning")
    if "mode" not in info:
        why.append("no summary lines found in log")
    severe = source_failure or incomplete_injuries or bool(info["error_lines"] or info["http_errors"]) or any(w.startswith("all ") for w in why)
    return ("degraded" if severe else ("warn" if why else "ok")), why


def gate_skipped(repo: str, run: dict, token: str) -> bool:
    """True when a scheduled run's time_gate job declined the slot and every producer job was skipped.

    GitHub fires both daylight-saving cron slots and often starts them hours late, so the
    off-slot tick can land after the real producer run. It does no work and is not evidence
    about the producer either way. Any other outcome (failure, cancellation, a producer job
    that ran, unreadable job list) is kept as a run so real problems stay visible.
    """
    if run.get("event") != "schedule" or run.get("conclusion") != "success":
        return False
    try:
        jobs = gh_json(f"/repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100", token).get("jobs", [])
    except Exception:  # noqa: BLE001
        return False
    gate = [j for j in jobs if j.get("name") == "time_gate"]
    producers = [j for j in jobs if j.get("name") not in ("time_gate", "pull_request_checks")]
    return (len(gate) == 1 and gate[0].get("conclusion") == "success" and bool(producers)
            and all(j.get("conclusion") == "skipped" for j in producers))


def workflow_health(repo: str, token: str, now: dt.datetime) -> list[dict]:
    out = []
    since = now - dt.timedelta(hours=LOOKBACK_HOURS)
    for fname, label in WORKFLOWS.items():
        entry: dict = {"workflow": label, "file": fname, "runs": []}
        try:
            runs = gh_json(f"/repos/{repo}/actions/workflows/{fname}/runs?per_page=30&status=completed&branch=main", token)
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"could not list runs: {exc}"
            out.append(entry)
            continue
        accepted_events = ("schedule", "workflow_dispatch", "workflow_run") if fname == "picks.yml" else ("schedule", "workflow_dispatch")
        # A guarded completion-triggered workflow may execute no producer at all.
        # Retain that observation, but do not replace actual producer evidence.
        skipped_chains = [r for r in runs.get("workflow_runs", [])
                          if fname == "picks.yml" and r.get("event") == "workflow_run"
                          and r.get("conclusion") == "skipped" and r.get("head_branch") == "main"]
        entry["skipped_chains"] = [{"run_id": r["id"], "url": r["html_url"],
                                    "created_at": r["created_at"]} for r in skipped_chains]
        candidates = [r for r in runs.get("workflow_runs", [])
                      if r["event"] in accepted_events and r.get("head_branch") == "main"
                      and r not in skipped_chains
                      and dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= since]
        # Off-slot scheduled ticks declined by the workflow's own time gate are observed, not judged.
        picked, gated = [], []
        for r in candidates:
            if len(picked) >= RUNS_PER_WORKFLOW:
                break
            (gated if fname == "context-calibrate.yml" and gate_skipped(repo, r, token) else picked).append(r)
        entry["gate_skipped"] = [{"run_id": r["id"], "url": r["html_url"],
                                  "created_at": r["created_at"]} for r in gated]
        for r in picked:
            info = None
            try:
                with zipfile.ZipFile(io.BytesIO(gh_logs_zip(repo, r["id"], token))) as z:
                    text = "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist()
                                     if n.endswith(".txt") and "/" not in n)
                info = parse_log(text)
            except Exception as exc:  # noqa: BLE001
                err = str(exc)[:120]
            else:
                err = None
            health, why = judge(label, r["conclusion"], info)
            run = {"run_id": r["id"], "url": r["html_url"], "event": r["event"],
                   "created_at": r["created_at"], "conclusion": r["conclusion"],
                   "health": health, "reasons": why}
            if info:
                run["summary"] = {k: v for k, v in info.items() if k not in ("error_lines",) and v not in ([], {}, None)}
                if info["error_lines"]:
                    run["error_lines"] = info["error_lines"]
            if err:
                run["log_read_error"] = err
            entry["runs"].append(run)
        entry["latest_health"] = entry["runs"][0]["health"] if entry["runs"] else "no_runs_in_window"
        out.append(entry)
    return out


def schedule_health(repo: str, token: str, now: dt.datetime) -> list[dict]:
    """Flag workflows whose last SCHEDULED run is older than the tolerated gap (missed cron slots)."""
    out = []
    for fname, (label, every_h, max_gap_h) in SCHEDULE_EXPECT.items():
        entry: dict = {"workflow": label, "file": fname, "expected_every_h": every_h, "max_gap_h": max_gap_h}
        gap = max_gap_h
        if fname == "injury-pull.yml" and now.weekday() not in (2, 3, 4, 5):  # Wed-Sat are weekday 2-5
            gap = 26
            entry["max_gap_h"] = gap
            entry["note"] = "Sun-Tue schedule is once a day"
        if fname == "grade-bim-board.yml" and now.weekday() not in (6, 0, 3, 4, 5):  # Sun, Mon, Thu, Fri, Sat run
            gap = 60
            entry["max_gap_h"] = gap
            entry["note"] = "Tue and Wed have no scheduled runs"
        try:
            runs = gh_json(f"/repos/{repo}/actions/workflows/{fname}/runs?per_page=30&event=schedule", token)
        except Exception as exc:  # noqa: BLE001
            entry.update(status="unknown", error=f"could not list runs: {exc}"[:160])
            out.append(entry)
            continue
        sched = runs.get("workflow_runs", [])
        if not sched:
            entry.update(status="no_scheduled_runs_found", last_scheduled_run_utc=None)
        else:
            last = max(dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) for r in sched)
            age = (now - last).total_seconds() / 3600
            entry.update(last_scheduled_run_utc=last.strftime("%Y-%m-%dT%H:%M:%SZ"), age_h=round(age, 1),
                         status="ok" if age <= gap else "missed")
        out.append(entry)
    return out


def main() -> None:
    token = os.environ.get("AIRTABLE_TOKEN", "").strip()
    base = os.environ.get("AIRTABLE_BASE_ID", "").strip()
    gh_token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not (token and base):
        raise SystemExit("ERROR: AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.")
    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(CENTRAL).date()

    graded = fetch(base, token, "AND({Record Type}='Game',OR({Grade}='Win',{Grade}='Loss',{Grade}='Push'))")
    n = write_graded_csv(graded)
    window = fetch(base, token, "AND({Record Type}='Game',IS_AFTER({Date},DATEADD(TODAY(),-8,'days')))")
    status: dict = {
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_for_central_date": today.isoformat(),
        "graded_picks_csv_rows": n,
        "ledger_health": row_health(window, today, now),
    }
    if gh_token and repo:
        status["workflow_health"] = workflow_health(repo, gh_token, now)
        status["schedule_health"] = schedule_health(repo, gh_token, now)
    else:
        status["workflow_health"] = "unknown: GITHUB_TOKEN/GITHUB_REPOSITORY not set"
    status["how_to_read"] = ("workflow health: ok / warn / degraded / failed / unknown. 'success' "
                             "conclusions are judged from log text, not trusted. Postponed games and "
                             "schedule_health: ok / missed per workflow (last SCHEDULED run vs tolerated gap; manual runs do not count). "
                             "same-day games can appear in the ledger_health lists; they are leads, not verdicts.")
    with open(os.path.join(DATA, "ops_status.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(status, indent=1) + "\n")

    lines = [f"graded_picks.csv rows: {n}",
             f"ledger games on/after {today}: {status['ledger_health']['games_today_or_later']}"]
    for k, v in status["ledger_health"]["checks"].items():
        if v["count"]:
            lines.append(f"{k}: {v['count']}")
    if isinstance(status["workflow_health"], list):
        for w in status["workflow_health"]:
            lines.append(f"{w['workflow']}: latest={w.get('latest_health')} "
                         + "; ".join(f"{r['health']}({', '.join(r['reasons']) or 'clean'})" for r in w["runs"][:2]))
    for s in status.get("schedule_health", []):
        if s.get("status") != "ok":
            lines.append(f"SCHEDULE {s['workflow']}: {s.get('status')} (last scheduled run {s.get('last_scheduled_run_utc')}, "
                         f"{s.get('age_h', '?')} h ago, tolerated {s['max_gap_h']} h)")
    print("\n".join(lines))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("## Ops export\n\n" + "\n".join(f"- {x}" for x in lines) + "\n")


if __name__ == "__main__":
    main()
