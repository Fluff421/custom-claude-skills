#!/usr/bin/env python3
"""Phase 1 ESPN sync for the Signal Desk Ledger (Airtable).

Pulls, for upcoming ledger Game rows: ESPN FPI, ESPN consensus line, neutral-site flag and
(NFL) injuries. Never touches Splash-sheet fields. Dry run by default (ESPN_SYNC_LIVE=1 to write).
"""
from __future__ import annotations

import datetime as dt
import html.parser
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ESPN = "https://site.api.espn.com/apis/site/v2/sports/football"
SCOREBOARDS = {
    "NFL": [ESPN + "/nfl/scoreboard?limit=100&dates={rng}"],
    "NCAAF": [
        ESPN + "/college-football/scoreboard?groups=80&limit=300&dates={rng}",
        ESPN + "/college-football/scoreboard?groups=81&limit=300&dates={rng}",
    ],
}
POWER_INDEX = ("https://sports.core.api.espn.com/v2/sports/football/leagues/{lg}/seasons/{season}"
               "/powerindex?limit=100&page={page}")
FPI_LEAGUE_PATH = {"NCAAF": "college-football", "NFL": "nfl"}
FPI_STALE_HOURS = 72
# Decimals stored in Home/Away FPI. 1 matches the ESPN display value the ledger has
# always used, so switching sources does not move games across tier lines.
FPI_DECIMALS = int(os.environ.get("FPI_DECIMALS", "1"))
FPI_PAGES = {"NCAAF": "https://www.espn.com/college-football/fpi", "NFL": "https://www.espn.com/nfl/fpi"}
NFL_INJURIES = ESPN + "/nfl/injuries"
SCRAPER_URL = "https://api.webscraping.ai/html"
HFA = {"NCAAF": 2.5, "NFL": 2.0}
LEDGER_DEFAULT = "tbl3tFHFhvyNMpksE"
KEEP_STATUS = ("out", "doubtful", "questionable")
ALIASES = {
    "floridainternational": ["fiu"],
    "fiu": ["floridainternational"],
    "louisianamonroe": ["ulmonroe"],
    "ulm": ["louisianamonroe", "ulmonroe"],
    "ulmonroe": ["louisianamonroe"],
    "appalachianstate": ["appstate"],
    "appstate": ["appalachianstate"],
    "miamifl": ["miami"],
    "southernmiss": ["southernmississippi"],
    "mississippistate": ["mississippistate"],
    "olemiss": ["mississippi"],
}
WARNINGS: list[str] = []


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print("WARN:", msg, file=sys.stderr)


def norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower().replace("&", ""))


def names_for(team: dict) -> set[str]:
    keys = ("location", "displayName", "shortDisplayName", "name")
    return {norm(team.get(k, "")) for k in keys if team.get(k)}


def ledger_matches(ledger_name: str, candidates: set[str]) -> bool:
    n = norm(ledger_name)
    return n in candidates or any(a in candidates for a in ALIASES.get(n, []))


def http_get(url: str, headers: dict | None = None, method: str = "GET", payload: dict | None = None) -> str:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} from {urllib.parse.urlparse(url).netloc}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error contacting {urllib.parse.urlparse(url).netloc}: {exc.reason}") from exc


def scrape(url: str, key: str, js: bool = False) -> str:
    time.sleep(1.5)  # stay polite: ESPN 403s rapid sequential requests
    params = urllib.parse.urlencode({"api_key": key, "url": url, "js": "true" if js else "false", "proxy": "datacenter"})
    return http_get(f"{SCRAPER_URL}?{params}")


def parse_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


# ---------- Airtable ----------
def at_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def at_list(base: str, table: str, token: str) -> list[dict]:
    formula = "AND({Record Type}='Game',IS_AFTER({Date},DATEADD(TODAY(),-1,'days')))"
    out, offset = [], None
    while True:
        url = f"https://api.airtable.com/v0/{base}/{table}?pageSize=100&filterByFormula=" + urllib.parse.quote(formula)
        if offset:
            url += "&offset=" + urllib.parse.quote(offset, safe="")
        page = json.loads(http_get(url, at_headers(token)))
        out.extend(page.get("records", []))
        offset = page.get("offset")
        if not offset:
            return out


def at_patch(base: str, table: str, token: str, updates: list[dict]) -> None:
    for i in range(0, len(updates), 10):
        http_get(f"https://api.airtable.com/v0/{base}/{table}", at_headers(token), "PATCH",
                 {"records": updates[i:i + 10], "typecast": True})


# ---------- ESPN scoreboard / lines ----------
def espn_events(league: str, dates: list[str], key: str) -> list[dict]:
    """Query ESPN's scoreboard one date at a time: multi-day ranges return no events.
    Each ledger date is queried together with the following day, so late kickoffs that
    spill into the next UTC day are still found. Events are deduped by ESPN event id."""
    events, seen = [], set()
    for date in dates:
        for template in SCOREBOARDS[league]:
            try:
                payload = parse_json(scrape(template.format(rng=date), key))
            except Exception as exc:  # noqa: BLE001
                warn(f"{league} scoreboard fetch failed for {date}: {exc}")
                continue
            for ev in payload.get("events", []):
                if ev.get("id") and ev["id"] not in seen:
                    seen.add(ev["id"])
                    events.append(ev)
    return events


def competitors(event: dict) -> dict:
    comp = (event.get("competitions") or [{}])[0]
    sides = {}
    for c in comp.get("competitors", []):
        if c.get("homeAway") in ("home", "away"):
            sides[c["homeAway"]] = c.get("team") or {}
    return {"comp": comp, "home": sides.get("home"), "away": sides.get("away")}


def home_spread(comp: dict, home_abbr: str, away_abbr: str) -> tuple[float | None, float | None, str]:
    odds = (comp.get("odds") or [None])[0]
    if not odds:
        return None, None, "ESPN has no odds for this game yet."
    provider = (odds.get("provider") or {}).get("name", "ESPN")
    total = odds.get("overUnder")
    details = (odds.get("details") or "").strip()
    spread, note = None, f"Provider: {provider}. Details: '{details}'."
    if details.upper() in {"EVEN", "PK", "PICK", "PICK'EM"}:
        spread = 0.0
    else:
        m = re.match(r"^(.+?)\s+([+-]?\d+(?:\.\d+)?)$", details)
        if m:
            fav, val = m.group(1).strip().upper(), float(m.group(2))
            val = -abs(val)
            if fav == home_abbr.upper():
                spread = val
            elif fav == away_abbr.upper():
                spread = -val
    if spread is None and odds.get("spread") is not None:
        s = abs(float(odds["spread"]))
        fav_home = (odds.get("homeTeamOdds") or {}).get("favorite")
        if fav_home is not None:
            spread, note = (-s if fav_home else s), note + " Spread taken from favorite flag."
    if spread is None:
        note += " Could not derive home spread."
    return spread, (float(total) if total is not None else None), note


def match_event(row: dict, events: list[dict]):
    f = row["fields"]
    home, away = f.get("Home Team", ""), f.get("Away Team", "")
    best = None
    for ev in events:
        c = competitors(ev)
        if not c["home"] or not c["away"]:
            continue
        hn, an = names_for(c["home"]), names_for(c["away"])
        neutral = bool(c["comp"].get("neutralSite"))
        straight = ledger_matches(home, hn) and ledger_matches(away, an)
        swapped = neutral and ledger_matches(home, an) and ledger_matches(away, hn)
        if straight or swapped:
            best = (ev, c, swapped)
            break
    return best


# ---------- FPI ----------
class Tables(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[list[str]]]] = []
        self._t = self._r = self._c = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._t = []
        elif tag == "tr" and self._t is not None:
            self._r = []
        elif tag in ("td", "th") and self._r is not None:
            self._c = []

    def handle_data(self, data):
        if self._c is not None and data.strip():
            self._c.append(data.strip())

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._c is not None and self._r is not None:
            self._r.append(self._c)
            self._c = None
        elif tag == "tr" and self._r is not None and self._t is not None:
            self._t.append(self._r)
            self._r = None
        elif tag == "table" and self._t is not None:
            self.tables.append(self._t)
            self._t = None


def _join_cell(cell: list[str]) -> str:
    """Join the letter-spaced data chunks ESPN's FPI page emits into one value."""
    return re.sub(r"\s+", " ", "".join(cell)).strip()


def parse_fpi(page: str) -> tuple[dict[str, float], str | None]:
    parser = Tables()
    parser.feed(page)
    updated = None
    m = re.search(r"Last Updated:?\s*([A-Za-z]+ \d{1,2}, \d{4})", re.sub(r"<[^>]+>", " ", page))
    if m:
        updated = m.group(1)
    out: dict[str, float] = {}
    # ESPN's FPI page renders team names and stats as two parallel tables (row i = team i).
    # Rows are letter-spaced, so chunks are joined back together before use.
    for table in parser.tables:
        rows = [r for r in table if r]
        if len(rows) < 8:
            continue
        # stats rows: second cell parses as a float (header rows fail and are skipped)
        if not all(len(r) >= 2 for r in rows):
            continue
        stats_rows = []
        for r in rows:
            try:
                stats_rows.append(float(_join_cell(r[1])))
            except ValueError:
                continue
        if len(stats_rows) < 8:
            continue
        # find the matching names table: same table length, rows carry text in the first cell.
        # The tables are zipped by RAW row position (both start with header rows), so
        # header filtering cannot shift one table relative to the other.
        for other in parser.tables:
            if other is table or len(other) != len(table):
                continue
            out = {}
            for nrow, srow in zip(other, table):
                if not nrow or not srow or not nrow[0] or len(srow) < 2:
                    continue
                n = _join_cell(nrow[0])
                if not n or n.upper() in ("TEAM", "W - L"):
                    continue
                try:
                    val = float(_join_cell(srow[1]))
                except ValueError:
                    continue
                out[norm(n)] = val
            if out:
                return out, updated
    # legacy fallback: single-table layouts
    names, stats = [], []
    for table in parser.tables:
        rows = [r for r in table if r]
        if len(rows) < 8:
            continue
        if all(len(r) == 1 for r in rows[1:]):
            names = [r[0][-1] for r in rows[1:]]
        else:
            numeric = []
            for r in rows:
                cells = [" ".join(c) for c in r]
                if len(cells) >= 3:
                    try:
                        numeric.append(float(cells[1]))
                    except ValueError:
                        continue
            if len(numeric) >= 8:
                stats = numeric
    if names and len(names) == len(stats):
        return {norm(n): v for n, v in zip(names, stats)}, updated
    return {}, updated


def load_fpi(league: str, key: str) -> dict[str, float]:
    for js in (False, True):
        try:
            data, updated = parse_fpi(scrape(FPI_PAGES[league], key, js=js))
        except Exception as exc:  # noqa: BLE001
            warn(f"{league} FPI fetch failed (js={js}): {exc}")
            continue
        if data:
            if updated:
                try:
                    age = (dt.date.today() - dt.datetime.strptime(updated, "%B %d, %Y").date()).days
                    if age > 3:
                        warn(f"{league} FPI page says Last Updated {updated} ({age} days old).")
                except ValueError:
                    pass
            return data
    warn(f"{league} FPI could not be parsed (layout may have changed). Please paste FPI manually for {league}.")
    return {}


def _team_id_from_ref(ref: str) -> str | None:
    m = re.search(r"/teams/(\d+)", ref or "")
    return m.group(1) if m else None


def _get_json(url: str, key: str):
    """Direct fetch first (core API needs no key); WebScraping.AI as fallback."""
    try:
        return json.loads(http_get(url, {"User-Agent": "Mozilla/5.0 signal-desk"}))
    except Exception as exc:  # noqa: BLE001
        if not key:
            raise
        warn(f"Direct fetch failed ({exc}); retrying via scraper.")
        return parse_json(scrape(url, key))


def load_fpi_index(league: str, key: str, season: int | None = None) -> dict[str, float]:
    """ESPN Core power index JSON, keyed by ESPN team id (same id as scoreboard
    competitors[].team.id). Freshness uses lastUpdated; runDateTimeKey is logged only,
    because the NCAAF value is known to carry stale metadata."""
    if season is None:
        today = dt.date.today()
        season = today.year if today.month >= 3 else today.year - 1  # Jan/Feb belong to last season
    out: dict[str, float] = {}
    updated: set[str] = set()
    run_keys: set[str] = set()
    page, pages = 1, 1
    while page <= pages:
        url = POWER_INDEX.format(lg=FPI_LEAGUE_PATH[league], season=season, page=page)
        try:
            payload = _get_json(url, key)
        except Exception as exc:  # noqa: BLE001
            warn(f"{league} power index fetch failed (page {page}): {exc}")
            return {}
        pages = int(payload.get("pageCount") or 1)
        for item in payload.get("items", []):
            tid = _team_id_from_ref((item.get("team") or {}).get("$ref", ""))
            fpi = next((p.get("value") for p in item.get("predictives", []) if p.get("name") == "fpi"), None)
            if tid and fpi is not None:
                out[tid] = round(float(fpi), FPI_DECIMALS)
            if item.get("lastUpdated"):
                updated.add(item["lastUpdated"])
            if item.get("runDateTimeKey"):
                run_keys.add(str(item["runDateTimeKey"]))
        page += 1
    if updated:
        newest = max(updated)
        try:
            ts = dt.datetime.strptime(newest, "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
            age_h = (dt.datetime.now(dt.timezone.utc) - ts).total_seconds() / 3600
            print(f"{league} power index: {len(out)} teams, lastUpdated {newest} ({age_h:.0f} h old), "
                  f"runDateTimeKey {sorted(run_keys)}")
            if age_h > FPI_STALE_HOURS:
                warn(f"{league} FPI is stale: lastUpdated {newest} ({age_h:.0f} h old).")
        except ValueError:
            warn(f"{league} power index lastUpdated not parseable: {newest}")
    else:
        warn(f"{league} power index has no lastUpdated; freshness unknown.")
    return out


def fpi_for(name: str, team: dict | None, fpi: dict[str, float]):
    keys = set(names_for(team)) if team else set()
    keys.add(norm(name))
    keys.update(ALIASES.get(norm(name), []))
    for k in keys:
        if k in fpi:
            return fpi[k]
    # unique-prefix fallback: ledger short name vs FPI full name with mascot
    # (e.g. "Ohio State" -> "Ohio State Buckeyes"); ambiguous prefixes are left unmatched
    n = norm(name)
    for cand in [n] + ALIASES.get(n, []):
        hits = {k: v for k, v in fpi.items() if k.startswith(cand)}
        if len(hits) == 1:
            return next(iter(hits.values()))
    return None


# ---------- injuries ----------
def load_nfl_injuries(key: str) -> dict[str, list[str]]:
    try:
        payload = parse_json(scrape(NFL_INJURIES, key))
    except Exception as exc:  # noqa: BLE001
        warn(f"NFL injuries fetch failed: {exc}")
        return {}
    out: dict[str, list[str]] = {}
    for team in payload.get("injuries", []):
        items = []
        for inj in team.get("injuries", []):
            status = (inj.get("status") or "").strip()
            if status.lower() not in KEEP_STATUS:
                continue
            ath = inj.get("athlete") or {}
            pos = (ath.get("position") or {}).get("abbreviation", "")
            items.append(f"{ath.get('displayName', '?')} ({pos}) {status}".replace(" ()", ""))
        out[norm(team.get("displayName", ""))] = items
    return out


# ---------- main ----------
def close(a, b) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, str) or isinstance(b, str):
        return a == b  # text fields compare by equality, never as numbers
    return abs(float(a) - float(b)) < 1e-6


def main() -> None:
    token = os.environ.get("AIRTABLE_TOKEN", "").strip()
    base = os.environ.get("AIRTABLE_BASE_ID", "").strip()
    table = os.environ.get("LEDGER_TABLE_ID", "").strip() or LEDGER_DEFAULT
    key = os.environ.get("WEBSCRAPING_AI_API_KEY", "").strip()
    live = os.environ.get("ESPN_SYNC_LIVE", "0").strip() == "1"
    if not (token and base and key):
        raise SystemExit("ERROR: AIRTABLE_TOKEN, AIRTABLE_BASE_ID and WEBSCRAPING_AI_API_KEY must be set.")
    try:
        rows = at_list(base, table, token)
    except RuntimeError as exc:
        raise SystemExit(f"ERROR reading ledger {table} in {base}. The secrets may point at a different base: {exc}")
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    updates, report, unmatched = [], [], []
    by_league: dict[str, list[dict]] = {}
    for r in rows:
        by_league.setdefault(r["fields"].get("League", ""), []).append(r)
    for league, lrows in by_league.items():
        if league not in SCOREBOARDS:
            continue
        ledger_dates = sorted({r["fields"]["Date"][:10].replace("-", "") for r in lrows if r["fields"].get("Date")})
        # add the day after each ledger date to catch late kickoffs that roll into the next UTC day
        query_dates = sorted({d for d in ledger_dates} | {
            (dt.datetime.strptime(d, "%Y%m%d") + dt.timedelta(days=1)).strftime("%Y%m%d") for d in ledger_dates
        })
        events = espn_events(league, query_dates, key)
        fpi_ids = load_fpi_index(league, key)
        fpi = {} if fpi_ids else load_fpi(league, key)  # HTML name match only if JSON fails
        if not fpi_ids and fpi:
            warn(f"{league}: power index JSON unavailable; fell back to FPI page name matching.")
        injuries = load_nfl_injuries(key) if league == "NFL" else {}
        if league == "NCAAF":
            warn("NCAAF injuries: no reliable ESPN league-wide feed; Injury Notes left blank (manual input needed).")
        for r in lrows:
            f = r["fields"]
            hit = match_event(r, events)
            if not hit:
                unmatched.append(f"{f.get('Game', r['id'])} ({league})")
                continue
            ev, c, swapped = hit
            home_t, away_t = (c["away"], c["home"]) if swapped else (c["home"], c["away"])
            neutral = bool(c["comp"].get("neutralSite"))
            spread, total, note = home_spread(c["comp"], home_t.get("abbreviation", ""), away_t.get("abbreviation", ""))
            new = {"ESPN Event ID": str(ev.get("id")), "ESPN Pulled At": now, "Neutral Site": neutral,
                   "HFA": 0.0 if neutral else HFA[league]}
            if spread is not None:
                new["ESPN Spread (Home)"] = spread
            if total is not None:
                new["ESPN Total"] = total
            splash = f.get("Vegas Implied Home Margin")
            if spread is not None and splash is not None:
                note += f" Splash vs ESPN home-margin gap: {float(splash) + spread:+.1f}."
            new["ESPN Line Note"] = note
            if fpi_ids:
                hf = fpi_ids.get(str(home_t.get("id") or ""))
                af = fpi_ids.get(str(away_t.get("id") or ""))
            else:
                hf, af = fpi_for(f.get("Home Team", ""), home_t, fpi), fpi_for(f.get("Away Team", ""), away_t, fpi)
            if hf is not None and af is not None:
                new["Home FPI"], new["Away FPI"] = hf, af
            elif fpi_ids or fpi:
                report.append(f"FPI missing for {f.get('Game')} (home={hf}, away={af}) - manual FPI needed")
            if league == "NFL" and injuries:
                parts = []
                for label, team in (("AWAY", away_t), ("HOME", home_t)):
                    items = injuries.get(norm(team.get("displayName", "")), [])
                    parts.append(f"{label}: " + ("; ".join(items[:8]) if items else "none listed"))
                new["Injury Notes"] = f"[ESPN {now[:16]}Z] " + " | ".join(parts)
            def same(k, v):
                cur = f.get(k)
                return (bool(cur) == v) if isinstance(v, bool) else (cur == v or close(cur, v))

            diff = {k: v for k, v in new.items() if k == "ESPN Pulled At" or not same(k, v)}
            if len(diff) == 1:
                diff.pop("ESPN Pulled At", None)
            if diff:
                updates.append({"id": r["id"], "fields": diff})
                report.append(f"{f.get('Game')}: " + ", ".join(k for k in diff if k != "ESPN Pulled At"))
    mode = "LIVE" if live else "DRY RUN"
    if live and updates:
        at_patch(base, table, token, updates)
    lines = [f"Mode: {mode}", f"Ledger rows scanned: {len(rows)}", f"Rows with changes: {len(updates)}"]
    lines += [f"Unmatched to ESPN: {len(unmatched)} - " + "; ".join(unmatched[:25])] if unmatched else []
    lines += [f"WARNING: {w}" for w in WARNINGS] + report[:60]
    print("\n".join(lines))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("## ESPN sync\n\n" + "\n".join(f"- {x}" for x in lines) + "\n")


if __name__ == "__main__":
    main()
