#!/usr/bin/env python3
"""Splash line history: validate a File 1 line dump, match it to the ledger and append it to the line log.

Splash Sports has no API, so every line dump the owner pastes (File 1, schema signal-desk.splash-lines.v1) is a
timestamped snapshot of the Splash board. This script turns those snapshots into a movement history so the system
can learn how Splash lines move before the owner picks.

Input (env SPLASH_LINES_DUMP): the File 1 JSON, raw, inside a ```json fence, or "gz:" + base64(gzip(json)) so a
large dump fits in a workflow input. Optional env SPLASH_SNAPSHOT_KIND (early_import | movement; default: the first
snapshot of a game's week is the early import, later ones are movement), SPLASH_ALLOW_STALE=1 (seeding only).

Writes (repo only, never Airtable):
  intelligence/splash_lines_log.csv            one row per game per snapshot, with movement and context columns
  intelligence/splash_lines/raw/<date_code>.json   the raw dump as received
  intelligence/splash_lines/<date_code>.md and latest.md   the movement report

Rules (see MODEL.md "Splash lines and the locked line"):
- The ledger's Vegas Implied Home Margin / Over/Under Line hold the early-week import and are never overwritten here.
- Validation rejects the whole dump on a failed check and never patches values. One exception: if game_count does
  not match, the dump is accepted when every game missing compared with the previous snapshot is already final in the
  ledger (Splash drops finished games); the count gap is reported.
- Each later snapshot is line movement. Context columns record what else moved (the sportsbook line from
  markets/lines_log.csv, injury notes, key numbers) so the movement can be discussed and learned from.
"""
from __future__ import annotations

import base64
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OUT = os.path.join(HERE, "intelligence")
LOG = os.path.join(OUT, "splash_lines_log.csv")
DIR = os.path.join(OUT, "splash_lines")
MARKET_LOG = os.path.join(OUT, "markets", "lines_log.csv")
PICKS_LATEST = os.path.join(OUT, "markets", "picks_latest.json")
SCHEMA, SOURCE = "signal-desk.splash-lines.v1", "Splash Sports Lines"
MAX_AGE_H = 24
NFL_KEYS = (3, 7, 10, 14)
NCAAF_KEYS = (3, 7, 10, 14, 17, 21)
NFL_TOTAL_KEYS = (37, 41, 43, 44, 47, 51)

COLS = ["snapshot_id", "snapshot_kind", "movement_seq", "captured_at_central", "captured_at_utc", "contest", "source_format",
        "league", "record_id", "game", "date", "kickoff_central", "hours_to_kickoff", "splash_away", "splash_home",
        "orientation", "home_margin", "total", "away_spread_price", "home_spread_price", "over_price", "under_price",
        "away_ml", "home_ml", "early_home_margin", "early_total", "prev_snapshot_id", "prev_home_margin", "prev_total",
        "d_margin_prev", "d_total_prev", "d_margin_early", "d_total_early", "moved_toward",
        "market_home_margin", "market_total", "market_ts", "market_d_margin_prev", "market_d_total_prev",
        "gap_vs_market_margin", "gap_vs_market_total", "key_numbers_crossed", "injury_hash", "injury_changed",
        "model_spread_side", "model_spread_tier", "model_total_side", "model_total_tier", "move_hint", "owner_note"]


# ---------------------------------------------------------------- parsing
def load_dump(text: str) -> dict:
    t = (text or "").strip()
    if t.startswith("gz:"):
        t = gzip.decompress(base64.b64decode(t[3:])).decode("utf-8")
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    elif "{" in t:
        t = t[t.index("{"): t.rindex("}") + 1]
    return json.loads(t)


def norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("&", ""))


def parse_utc(s: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def central_offset(day: dt.date) -> int:
    """Hours from UTC for US Central on that date (CDT -5 from the 2nd Sunday of March to the 1st Sunday of November)."""
    def nth_sunday(y, mth, n):
        d = dt.date(y, mth, 1)
        d += dt.timedelta(days=(6 - d.weekday()) % 7)
        return d + dt.timedelta(weeks=n - 1)
    return -5 if nth_sunday(day.year, 3, 2) <= day < nth_sunday(day.year, 11, 1) else -6


# ---------------------------------------------------------------- matching
def team_match(splash: str, ledger: str, league: str) -> bool:
    a, b = norm(splash), norm(ledger)
    if not a or not b:
        return False
    if a == b:
        return True
    if league == "NFL":   # Splash often shows NFL nicknames ("Bears", "49ers")
        words = re.findall(r"[A-Za-z0-9]+", ledger or "")
        return bool(words) and a == norm(words[-1])
    return False


def match_game(g: dict, games: list[dict]) -> tuple[dict | None, str, list[dict]]:
    """(ledger row, orientation 'same'|'reversed', all candidates). Exact names, league and kickoff date +/- 1 day."""
    try:
        kd = dt.date.fromisoformat((g.get("kickoff_central") or "")[:10])
    except ValueError:
        kd = None
    hits = []
    for f in games:
        if (f.get("League") or "") != g.get("league"):
            continue
        try:
            fd = dt.date.fromisoformat((f.get("Date") or "")[:10])
        except ValueError:
            continue
        if kd and abs((fd - kd).days) > 1:
            continue
        if team_match(g["home_team"], f.get("Home Team"), g["league"]) and team_match(g["away_team"], f.get("Away Team"), g["league"]):
            hits.append((f, "same"))
        elif team_match(g["home_team"], f.get("Away Team"), g["league"]) and team_match(g["away_team"], f.get("Home Team"), g["league"]):
            hits.append((f, "reversed"))
    if len(hits) == 1:
        return hits[0][0], hits[0][1], [h[0] for h in hits]
    return None, "", [h[0] for h in hits]


# ---------------------------------------------------------------- validation
def validate(d: dict, games: list[dict], prev_rows: list[dict], now: dt.datetime, allow_stale: bool = False) -> tuple[list[str], list[str]]:
    """Returns (errors, notes). Any error rejects the whole dump. Values are never patched."""
    errors, notes = [], []
    if d.get("schema") != SCHEMA:
        errors.append(f"schema is {d.get('schema')!r}, expected {SCHEMA}")
    if d.get("source") != SOURCE:
        errors.append(f"source is {d.get('source')!r}, expected {SOURCE!r}")
    for k in ("date_code", "extracted_at_utc"):
        if not d.get(k):
            errors.append(f"{k} is missing")
    ts = parse_utc(d.get("extracted_at_utc"))
    if d.get("extracted_at_utc") and ts is None:
        errors.append("extracted_at_utc does not parse")
    if ts and not allow_stale and (now - ts).total_seconds() > MAX_AGE_H * 3600:
        errors.append(f"dump is {(now - ts).total_seconds() / 3600:.1f} hours old (limit {MAX_AGE_H}); paste a fresh one")
    gl = d.get("games") or []
    if not gl:
        errors.append("no games in the dump")
    for g in gl:
        name = f"{g.get('away_team')} @ {g.get('home_team')}"
        try:
            if float(g["away_spread"]) != -float(g["home_spread"]):
                errors.append(f"{name}: away_spread {g['away_spread']} is not -home_spread {g['home_spread']}")
        except (KeyError, TypeError, ValueError):
            errors.append(f"{name}: spreads missing or not numbers")
        if g.get("total") is not None:
            try:
                float(g["total"])
            except (TypeError, ValueError):
                errors.append(f"{name}: total is not a number")
        if not re.match(r"^\d{4}-\d\d-\d\d( \d\d:\d\d)?$", g.get("kickoff_central") or ""):
            errors.append(f"{name}: kickoff_central {g.get('kickoff_central')!r} does not parse as Central time")
    present = {}
    for g in gl:
        present[g.get("league")] = present.get(g.get("league"), 0) + 1
    declared = d.get("game_count") or {}
    if any(int(declared.get(k, 0) or 0) != present.get(k, 0) for k in set(declared) | set(present)):
        # Accept only when everything missing versus the previous snapshot is already final in the ledger.
        by_id = {f["_id"]: f for f in games}
        now_ids = set()
        for g in gl:
            f, _, _ = match_game(g, games)
            if f:
                now_ids.add(f["_id"])
        prev_ids = {r["record_id"] for r in prev_rows if r.get("record_id")}
        missing = [by_id.get(i) for i in prev_ids - now_ids]
        not_final = [m for m in missing if not m or m.get("Home Score") is None]
        if prev_rows and not not_final:
            notes.append(f"game_count says {declared} but the dump has {present}. Every game missing since the previous snapshot is "
                         f"already final ({', '.join(sorted(m.get('Game', '') for m in missing)) or 'none'}), so the gap is a count "
                         "error or finished games Splash dropped; accepted.")
        else:
            errors.append(f"game_count says {declared} but the dump has {present}, and the gap is not explained by finished games")
    return errors, notes


# ---------------------------------------------------------------- context
def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def market_at(market_rows: list[dict], record_id: str, when: dt.datetime) -> dict | None:
    """The sportsbook line logged at or before `when` for this game (lines_log.csv only writes on change)."""
    best = None
    for r in market_rows:
        if r.get("record_id") != record_id:
            continue
        t = parse_utc(r.get("ts"))
        if t and t <= when and (best is None or t > best[0]):
            best = (t, r)
    return None if best is None else best[1]


def fnum(x) -> float | None:
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def crossed(a: float | None, b: float | None, keys: tuple) -> list[str]:
    if a is None or b is None or a == b:
        return []
    lo, hi = sorted((abs(a), abs(b)))
    out = [str(k) for k in keys if lo < k < hi or (k in (lo, hi) and lo != hi)]
    if (a > 0) != (b > 0) and a != 0 and b != 0:
        out.append("favorite flipped")
    return out


def injury_hash(f: dict) -> str:
    txt = " | ".join(str(f.get(k) or "") for k in ("Injury Notes", "QB Starter Note"))
    return hashlib.sha1(txt.encode()).hexdigest()[:10] if txt.strip(" |") else ""


def model_view(picks_latest: dict, record_id: str) -> dict:
    for g in (picks_latest or {}).get("games", []):
        if g.get("game_id") == record_id:
            sp = next((p for p in g.get("picks", []) if p.get("market") == "spread"), {})
            to = next((p for p in g.get("picks", []) if p.get("market") == "total"), {})
            return {"model_spread_side": sp.get("team") or sp.get("side", ""), "model_spread_tier": sp.get("tier", ""),
                    "model_total_side": to.get("side", ""), "model_total_tier": to.get("tier", "")}
    return {}


def hint(r: dict) -> str:
    """Plain-words reason candidates for a move. These are hypotheses for discussion, not conclusions."""
    parts = []
    dm, dt_ = fnum(r.get("d_margin_prev")), fnum(r.get("d_total_prev"))
    mdm, mdt = fnum(r.get("market_d_margin_prev")), fnum(r.get("market_d_total_prev"))
    if r.get("snapshot_kind") == "early_import":
        return "early-week import (baseline)"
    if dm:
        if mdm and (mdm > 0) == (dm > 0):
            parts.append(f"spread followed the sportsbook move ({mdm:+g})")
        elif mdm and (mdm > 0) != (dm > 0):
            parts.append(f"spread moved against the sportsbook move ({mdm:+g}); possible Splash pool money or a stale board")
        elif fnum(r.get("gap_vs_market_margin")) is not None and abs(fnum(r["gap_vs_market_margin"])) < abs(fnum(r["gap_vs_market_margin"]) - dm):
            parts.append("spread caught up toward the sportsbook line")
        else:
            parts.append("Splash-only spread move (sportsbook flat)")
    if dt_:
        if mdt and (mdt > 0) == (dt_ > 0):
            parts.append(f"total followed the sportsbook move ({mdt:+g})")
        elif mdt:
            parts.append(f"total moved against the sportsbook move ({mdt:+g})")
        else:
            parts.append("Splash-only total move")
    if r.get("injury_changed") == "yes":
        parts.append("injury notes changed since the last snapshot")
    if r.get("key_numbers_crossed"):
        parts.append("crossed " + r["key_numbers_crossed"])
    return "; ".join(parts) or "no change"


# ---------------------------------------------------------------- build rows
def build_rows(d: dict, games: list[dict], prev_rows: list[dict], market_rows: list[dict], picks_latest: dict,
               kind_override: str | None = None, with_model: bool = True) -> tuple[list[dict], list[str], list[str]]:
    """Returns (rows, unmatched, flagged). with_model=False for seeded history (today's model view would be anachronistic)."""
    ts = parse_utc(d["extracted_at_utc"])
    rows, unmatched, flagged = [], [], []
    by_rec: dict[str, list[dict]] = {}
    for r in prev_rows:
        by_rec.setdefault(r.get("record_id"), []).append(r)
    for g in d.get("games", []):
        f, orient, cands = match_game(g, games)
        name = f"{g.get('away_team')} @ {g.get('home_team')}"
        if not f:
            unmatched.append(f"{name} ({g.get('league')}, {g.get('kickoff_central')})" + (f": {len(cands)} ledger rows matched" if cands else ""))
            continue
        home_spread = float(g["home_spread"])
        hm = -home_spread if orient == "same" else home_spread    # ledger orientation: positive = ledger home favored
        if orient == "reversed" or g.get("home_away_certain") is False:
            flagged.append(f"{f.get('Game')}: Splash lists {g.get('home_team')} as home" + (" (home/away not certain on the page)" if g.get("home_away_certain") is False else "")
                           + (f"; ledger says neutral site" if f.get("Neutral Site") else ""))
        hist = sorted(by_rec.get(f["_id"], []), key=lambda r: r.get("captured_at_utc", ""))
        hist = [r for r in hist if r.get("snapshot_id") != d["date_code"]]
        early = next((r for r in hist if r.get("snapshot_kind") == "early_import"), None)
        prev = hist[-1] if hist else None
        kind = kind_override or ("movement" if early else "early_import")
        seq = 0 if kind == "early_import" else 1 + sum(1 for r in hist if r.get("snapshot_kind") == "movement")
        tot = fnum(g.get("total"))
        e_m, e_t = (fnum(early["home_margin"]), fnum(early["total"])) if early else (hm, tot) if kind == "early_import" else (None, None)
        p_m, p_t = (fnum(prev["home_margin"]), fnum(prev["total"])) if prev else (None, None)
        mk_now = market_at(market_rows, f["_id"], ts)
        mk_prev = market_at(market_rows, f["_id"], parse_utc(prev["captured_at_utc"])) if prev and parse_utc(prev.get("captured_at_utc")) else None
        m_m, m_t = (fnum(mk_now.get("home_margin_line")), fnum(mk_now.get("total"))) if mk_now else (None, None)
        pm_m, pm_t = (fnum(mk_prev.get("home_margin_line")), fnum(mk_prev.get("total"))) if mk_prev else (None, None)
        try:
            ko_d = dt.datetime.fromisoformat(g["kickoff_central"]) if len(g["kickoff_central"]) > 10 else None
            ko_utc = (ko_d - dt.timedelta(hours=central_offset(ko_d.date()))).replace(tzinfo=dt.timezone.utc) if ko_d else None
            htk = round((ko_utc - ts).total_seconds() / 3600, 1) if ko_utc else ""
        except (ValueError, KeyError):
            htk = ""
        d_m = None if p_m is None else round(hm - p_m, 2)
        d_t = None if p_t is None or tot is None else round(tot - p_t, 2)
        keys = NFL_KEYS if g["league"] == "NFL" else NCAAF_KEYS
        kx = crossed(p_m, hm, keys) + ([f"total {k}" for k in NFL_TOTAL_KEYS if p_t is not None and tot is not None and g["league"] == "NFL"
                                        and min(p_t, tot) < k < max(p_t, tot)])
        ih = injury_hash(f)
        row = {"snapshot_id": d["date_code"], "snapshot_kind": kind, "movement_seq": seq,
               "captured_at_central": d.get("extracted_at_central", ""), "captured_at_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "contest": d.get("contest_name", ""), "source_format": d.get("source_format", "file1_json"),
               "league": g["league"], "record_id": f["_id"], "game": f.get("Game"), "date": (f.get("Date") or "")[:10],
               "kickoff_central": g.get("kickoff_central", ""), "hours_to_kickoff": htk,
               "splash_away": g.get("away_team"), "splash_home": g.get("home_team"), "orientation": orient,
               "home_margin": hm, "total": "" if tot is None else tot,
               "away_spread_price": g.get("away_spread_price", ""), "home_spread_price": g.get("home_spread_price", ""),
               "over_price": g.get("over_price", ""), "under_price": g.get("under_price", ""),
               "away_ml": g.get("away_ml", ""), "home_ml": g.get("home_ml", ""),
               "early_home_margin": "" if e_m is None else e_m, "early_total": "" if e_t is None else e_t,
               "prev_snapshot_id": prev.get("snapshot_id", "") if prev else "",
               "prev_home_margin": "" if p_m is None else p_m, "prev_total": "" if p_t is None else p_t,
               "d_margin_prev": "" if d_m is None else d_m, "d_total_prev": "" if d_t is None else d_t,
               "d_margin_early": "" if e_m is None else round(hm - e_m, 2),
               "d_total_early": "" if e_t is None or tot is None else round(tot - e_t, 2),
               "moved_toward": "" if not d_m else (f.get("Home Team") if d_m > 0 else f.get("Away Team")),
               "market_home_margin": "" if m_m is None else m_m, "market_total": "" if m_t is None else m_t,
               "market_ts": mk_now.get("ts", "") if mk_now else "",
               "market_d_margin_prev": "" if m_m is None or pm_m is None else round(m_m - pm_m, 2),
               "market_d_total_prev": "" if m_t is None or pm_t is None else round(m_t - pm_t, 2),
               "gap_vs_market_margin": "" if m_m is None else round(hm - m_m, 2),
               "gap_vs_market_total": "" if m_t is None or tot is None else round(tot - m_t, 2),
               "key_numbers_crossed": ", ".join(kx), "injury_hash": ih,
               "injury_changed": "" if not prev else ("yes" if prev.get("injury_hash", "") != ih and prev.get("injury_hash") is not None else "no"),
               "owner_note": ""}
        if with_model:
            row.update(model_view(picks_latest, f["_id"]))
        row["move_hint"] = hint(row)
        rows.append(row)
    return rows, unmatched, flagged


# ---------------------------------------------------------------- learning summary
def movement_learning(log_rows: list[dict], games_by_id: dict) -> list[list]:
    """For finished games: did the side the Splash line moved toward cover the EARLY line, and the latest line?"""
    out = {}
    latest: dict[str, dict] = {}
    for r in log_rows:
        if r.get("snapshot_kind") == "movement" and (r.get("record_id") not in latest or r["captured_at_utc"] > latest[r["record_id"]]["captured_at_utc"]):
            latest[r["record_id"]] = r
    for rid, r in latest.items():
        f = games_by_id.get(rid)
        if not f or f.get("Home Score") is None or f.get("Away Score") is None:
            continue
        dme = fnum(r.get("d_margin_early"))
        if not dme:
            continue
        margin = float(f["Home Score"]) - float(f["Away Score"])
        toward_home = dme > 0
        early = fnum(r.get("early_home_margin"))
        res = (margin - early) if toward_home else (early - margin)
        lg = r.get("league")
        s = out.setdefault(lg, [0, 0, 0])
        s[0] += 1
        s[1] += 1 if res > 0 else 0
        s[2] += 1 if res == 0 else 0
    return [[lg, n, w, p, f"{(w / (n - p) * 100):.0f}%" if n - p else "", "small sample" if n < 30 else ""] for lg, (n, w, p) in sorted(out.items())]


def render(d: dict, rows: list[dict], unmatched: list[str], flagged: list[str], notes: list[str], learning: list[list]) -> str:
    from intelligence_report import md_table
    moved = [r for r in rows if r["snapshot_kind"] == "movement" and (r["d_margin_prev"] not in ("", 0, 0.0) or r["d_total_prev"] not in ("", 0, 0.0))]
    kind = rows[0]["snapshot_kind"] if rows else ""
    L = [f"# Splash line snapshot {d['date_code']} ({d.get('extracted_at_central', '')})", "",
         f"{len(rows)} games logged from {d.get('contest_name') or 'Splash'}; snapshot type: {kind or 'n/a'}. "
         f"{len(moved)} games moved since the previous snapshot. The ledger keeps the early-week import; this log holds every later move. "
         "Move reasons below are hypotheses for discussion, not conclusions. Paper picks only; verify against your Splash line before locking.", ""]
    for n in notes:
        L += [f"Note: {n}", ""]
    if moved:
        L.append(md_table(["Game", "Spread (home margin) prev -> now", "Early", "Total prev -> now", "Sportsbook now", "Model side / tier", "Possible reason"],
                          [[r["game"], f"{r['prev_home_margin']} -> {r['home_margin']}", r["early_home_margin"], f"{r['prev_total']} -> {r['total']}",
                            f"{r['market_home_margin']} / {r['market_total']}", f"{r.get('model_spread_side', '')} {r.get('model_spread_tier', '')}; {r.get('model_total_side', '')} {r.get('model_total_tier', '')}",
                            r["move_hint"]] for r in moved]))
    keyx = [r for r in rows if r.get("key_numbers_crossed")]
    if keyx:
        L += ["", "Key numbers crossed: " + "; ".join(f"{r['game']} ({r['key_numbers_crossed']})" for r in keyx)]
    if flagged:
        L += ["", "Home/away flagged (not used for the ledger): " + "; ".join(flagged)]
    if unmatched:
        L += ["", "Not matched to a ledger game: " + "; ".join(unmatched)]
    if learning:
        L += ["", "What movement has meant so far (finished games; did the side the line moved toward cover the early line):", "",
              md_table(["League", "Games", "Covered", "Push", "Rate", "Caution"], learning)]
    return "\n".join(L) + "\n"


def write_log(rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    existing = read_csv(LOG)
    keep = [r for r in existing if r.get("snapshot_id") not in {x["snapshot_id"] for x in rows}]   # re-running a dump replaces it
    with open(LOG, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(keep + rows, key=lambda r: (r.get("captured_at_utc", ""), r.get("league", ""), r.get("date", ""), r.get("game", ""))))


def load_games() -> list[dict]:
    path = os.environ.get("LEDGER_JSON")
    if path:   # offline / tests: a JSON list of {"id", "fields"} records
        with open(path, encoding="utf-8") as fh:
            return [r["fields"] | {"_id": r["id"]} for r in json.load(fh)]
    import espn_sync as es
    import intelligence_report as ir
    token, base = os.environ.get("AIRTABLE_TOKEN", "").strip(), os.environ.get("AIRTABLE_BASE_ID", "").strip()
    if not (token and base):
        raise SystemExit("ERROR: AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set (or LEDGER_JSON for offline use).")
    es.AIRTABLE_BASE = base
    return [r["fields"] | {"_id": r["id"]} for r in ir.fetch(base, token, ir.LEDGER, "{Record Type}='Game'")]


def main() -> None:
    raw = os.environ.get("SPLASH_LINES_DUMP", "")
    if not raw.strip() and os.environ.get("SPLASH_LINES_FILE"):
        with open(os.environ["SPLASH_LINES_FILE"], encoding="utf-8") as fh:
            raw = fh.read()
    try:
        d = load_dump(raw)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"REJECTED: the dump is not readable JSON ({exc}).")
    games = load_games()
    log_rows = read_csv(LOG)
    prev_snap = sorted({(r["captured_at_utc"], r["snapshot_id"]) for r in log_rows if r.get("snapshot_id") != d.get("date_code")})
    prev_rows = [r for r in log_rows if prev_snap and r["snapshot_id"] == prev_snap[-1][1]]
    now = dt.datetime.now(dt.timezone.utc)
    errors, notes = validate(d, games, prev_rows, now, os.environ.get("SPLASH_ALLOW_STALE") == "1")
    if errors:
        print("REJECTED. Nothing was logged. Reasons:\n- " + "\n- ".join(errors))
        raise SystemExit(1)
    picks_latest = {}
    if os.path.exists(PICKS_LATEST):
        with open(PICKS_LATEST, encoding="utf-8") as fh:
            picks_latest = json.load(fh)
    rows, unmatched, flagged = build_rows(d, games, [r for r in log_rows if r.get("snapshot_id") != d["date_code"]],
                                          read_csv(MARKET_LOG), picks_latest, os.environ.get("SPLASH_SNAPSHOT_KIND") or None,
                                          with_model=os.environ.get("SPLASH_ALLOW_STALE") != "1")
    write_log(rows)
    os.makedirs(os.path.join(DIR, "raw"), exist_ok=True)
    with open(os.path.join(DIR, "raw", f"{d['date_code']}.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1)
    learning = movement_learning(read_csv(LOG), {f["_id"]: f for f in games})
    text = render(d, rows, unmatched, flagged, notes, learning)
    for name in (f"{d['date_code']}.md", "latest.md"):
        with open(os.path.join(DIR, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
