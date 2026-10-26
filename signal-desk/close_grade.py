"""Phase 2 for the Signal Desk: closing-line capture, auto-grading, CLV, pool-leg
grading and Calibration Log tallies.

Runs hourly. For each ledger Game row:
  1. Closing capture - within ~3h of kickoff (or once live), the current/last ESPN
     line is written to Closing Spread (Home) / Over/Under Line if blank.
  2. Grading - once ESPN reports the game final and scores are still blank, write
     scores, margin, Spread/O-U results, pick grade (Win/Loss/Push) and pick CLV.
  3. Pool legs - grade Pending legs from finals, backfill Final Score / Closing
     Line / CLV where possible, then settle the parent Pool Bets ticket.
  4. Calibration Log - upsert per sport/week/tier tallies (never overwrites
     existing Est. Win Prob, Notes or Dates).

Never touches Splash fields or already-graded rows. Dry run by default
(CLOSE_GRADE_LIVE=1 to write).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import espn_sync as es  # shared helpers: http_get, scrape, parse_json, norm, ...

LEDGER = "tbl3tFHFhvyNMpksE"
LEGS = "tbl8xIdmwCpmLWwWV"
BETS = "tblGzA7EbNsgVHflY"
CALIB = "tblN7NyoPdOve792d"
POOL_NAME = "Gus' Staredown Showdown '26"
# season anchors: NCAAF week-1 Saturday and NFL week-1 Tuesday (2026 season)
NCAAF_W1_SAT = dt.date(2026, 9, 5)
NFL_W1_TUE = dt.date(2026, 9, 8)
CLOSE_WINDOW = dt.timedelta(hours=3)


def week_of(date_str: str, league: str) -> int:
    d = dt.date.fromisoformat(date_str[:10])
    if league == "NFL":
        return max(1, (d - NFL_W1_TUE).days // 7 + 1)
    return max(1, ((d - NCAAF_W1_SAT).days + 5) // 7 + 1)


def at_list_all(table: str, token: str, formula: str = "TRUE()") -> list[dict]:
    out, offset = [], None
    while True:
        url = f"https://api.airtable.com/v0/{es.AIRTABLE_BASE}/{table}?pageSize=100&filterByFormula=" + \
            urllib.parse.quote(formula)
        if offset:
            url += "&offset=" + urllib.parse.quote(offset, safe="")
        page = json.loads(es.http_get(url, es.at_headers(token)))
        out.extend(page.get("records", []))
        offset = page.get("offset")
        if not offset:
            return out


def at_write(token: str, patches: list[dict] | None = None, creates: list[dict] | None = None,
             table: str = LEDGER) -> None:
    if patches:
        for i in range(0, len(patches), 10):
            es.http_get(f"https://api.airtable.com/v0/{es.AIRTABLE_BASE}/{table}", es.at_headers(token), "PATCH",
                       {"records": patches[i:i + 10], "typecast": True})
    if creates:
        for i in range(0, len(creates), 10):
            es.http_get(f"https://api.airtable.com/v0/{es.AIRTABLE_BASE}/{table}", es.at_headers(token), "POST",
                        {"records": creates[i:i + 10], "typecast": True})


# ---------- pick parsing ----------
PICK_RE = re.compile(r"^(.+?)\s+([+-]?\d+(?:\.\d+)?)\s*\((spread|total)\)$")
LEG_TOTAL_RE = re.compile(r"^(over|under)\s+(\d+(?:\.\d+)?)$", re.I)
LEG_SPREAD_RE = re.compile(r"^(.+?)\s+([+-]\d+(?:\.\d+)?)$")


def parse_pick(rec_side: str):
    """'Clemson -2.5 (spread)' -> ('spread', 'Clemson', -2.5); 'Under 60.5 (total)' -> ('total','under',60.5)."""
    m = PICK_RE.match((rec_side or "").strip())
    if not m:
        return None
    team, line, kind = m.group(1).strip(), float(m.group(2)), m.group(3)
    if kind == "total":
        return ("total", team.lower(), line)
    return ("spread", team, line)


def side_is_home(team: str, home: str, away: str) -> bool | None:
    n = es.norm(team)
    if es.ledger_matches(home, {n}) or es.ledger_matches(team, es.names_for({"displayName": home})):
        return True
    if es.ledger_matches(away, {n}) or es.ledger_matches(team, es.names_for({"displayName": away})):
        return False
    return None


def grade_spread_pick(margin: float, line: float, is_home: bool) -> str:
    """line is the pick-side line (negative = team favored). Push on exact."""
    adj = margin + line if is_home else -margin + line
    return "Won" if adj > 0 else ("Lost" if adj < 0 else "Push")


def grade_total_pick(points: float, line: float, side: str) -> str:
    if points == line:
        return "Push"
    over = points > line
    return ("Won" if over else "Lost") if side == "over" else ("Lost" if over else "Won")


def spread_result(margin: float, home_spread: float) -> str:
    adj = margin + home_spread
    return "Home Covered" if adj > 0 else ("Away Covered" if adj < 0 else "Push")


def ou_result(points: float, total: float) -> str:
    return "Over" if points > total else ("Under" if points < total else "Push")


def closing_pick_line(closing_home_spread: float, is_home: bool) -> float:
    return closing_home_spread if is_home else -closing_home_spread


def append_note(existing: str | None, line: str) -> str:
    return ((existing or "").rstrip() + ("\n" if existing else "") + line)


# ---------- main ----------
def main() -> None:
    token = os.environ.get("AIRTABLE_TOKEN", "").strip()
    base = os.environ.get("AIRTABLE_BASE_ID", "").strip() or os.environ.get("SIGNAL_DESK_BASE_ID", "").strip()
    es.AIRTABLE_BASE = base
    key = os.environ.get("WEBSCRAPING_AI_API_KEY", "").strip()
    live = os.environ.get("CLOSE_GRADE_LIVE", "0").strip() == "1"
    if not (token and base and key):
        raise SystemExit("ERROR: AIRTABLE_TOKEN, AIRTABLE_BASE_ID and WEBSCRAPING_AI_API_KEY must be set.")

    now = dt.datetime.now(dt.timezone.utc)
    rows = at_list_all(LEDGER, token,
                       "AND({Record Type}='Game',IS_AFTER({Date},DATEADD(TODAY(),-4,'days')))")
    report: list[str] = []
    ledger_patches: list[dict] = []
    graded_margins: dict[str, dict] = {}  # "awaynorm@homenorm" -> grading info for pool legs

    by_league: dict[str, list[dict]] = {}
    for r in rows:
        by_league.setdefault(r["fields"].get("League", ""), []).append(r)

    for league, lrows in by_league.items():
        if league not in es.SCOREBOARDS:
            continue
        dates = sorted({r["fields"]["Date"][:10].replace("-", "") for r in lrows if r["fields"].get("Date")})
        query_dates = sorted(set(dates) | {
            (dt.datetime.strptime(d, "%Y%m%d") + dt.timedelta(days=1)).strftime("%Y%m%d") for d in dates})
        try:
            events = es.espn_events(league, query_dates, key)
        except Exception as exc:  # noqa: BLE001
            es.warn(f"{league} scoreboard fetch failed: {exc}")
            continue
        by_event = {str(ev.get("id")): ev for ev in events}
        for r in lrows:
            f = r["fields"]
            if not f.get("ESPN Event ID") or str(f.get("ESPN Event ID")) not in by_event:
                continue
            ev = by_event[str(f["ESPN Event ID"])]
            c = es.competitors(ev)
            if not c["home"] or not c["away"]:
                continue
            state = ((ev.get("status") or {}).get("type") or {}).get("state")
            completed = ((ev.get("status") or {}).get("type") or {}).get("completed", False)
            try:
                kickoff = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                kickoff = None
            home_name, away_name = f.get("Home Team", ""), f.get("Away Team", "")

            # --- closing capture (only into blank fields) ---
            if f.get("Closing Spread (Home)") is None and state in ("pre", "in"):
                if kickoff and (state == "in" or kickoff - now <= CLOSE_WINDOW):
                    spread, total, note = es.home_spread(c["comp"], c["home"].get("abbreviation", ""),
                                                         c["away"].get("abbreviation", ""))
                    if spread is None and f.get("ESPN Spread (Home)") is not None:
                        spread = float(f["ESPN Spread (Home)"])
                        note = "fallback to last pre-game pull"
                    if total is None and f.get("ESPN Total") is not None:
                        total = float(f["ESPN Total"])
                    if spread is not None:
                        fav = "EVEN" if spread == 0 else (home_name if spread < 0 else away_name)
                        new = {"Closing Spread (Home)": spread, "Closing Favorite": fav}
                        if total is not None:
                            new["Over/Under Line"] = total
                        new["Line Source Note"] = append_note(
                            f.get("Line Source Note"),
                            f"Closing captured {now.strftime('%Y-%m-%d %H:%MZ')} "
                            f"({'pre-kickoff' if state == 'pre' else 'live, last pre-game pull'}), ESPN/DraftKings. {note}")
                        ledger_patches.append({"id": r["id"], "fields": new})
                        report.append(f"{f.get('Game')}: closing line captured (home spread {spread:+g}"
                                      + (f", total {total:g}" if total else "") + ")")

            # --- grading (only when scores blank and game final) ---
            if state == "post" and completed and f.get("Home Score") is None:
                scores = {}
                for side in c["comp"].get("competitors", []):
                    if side.get("homeAway") in ("home", "away"):
                        scores[side["homeAway"]] = side.get("score")
                if scores.get("home") is None:
                    continue
                hs, aw = float(scores["home"]), float(scores.get("away") or 0)
                margin = hs - aw
                new = {"Home Score": hs, "Away Score": aw, "Actual Home Margin": margin}
                notes = [f"Final (ESPN auto-grade {now.strftime('%Y-%m-%d %H:%MZ')}): event {ev.get('id')}."]
                close_spread = f.get("Closing Spread (Home)")
                used_close = "closing line"
                if close_spread is None and f.get("ESPN Spread (Home)") is not None:
                    close_spread = float(f["ESPN Spread (Home)"])
                    used_close = "last ESPN pre-game pull (no closing captured)"
                if close_spread is not None:
                    new["Spread Result"] = spread_result(margin, float(close_spread))
                else:
                    new["Spread Result"] = "No Line"
                close_total = f.get("Over/Under Line")
                if close_total is None and f.get("ESPN Total") is not None:
                    close_total = float(f["ESPN Total"])
                if close_total is not None:
                    new["O/U Result"] = ou_result(hs + aw, float(close_total))
                else:
                    new["O/U Result"] = "No Line"
                # pick grade + CLV
                pick = parse_pick(f.get("Recommended Side") or "")
                if pick and f.get("Sharp-Sheet Tier"):
                    kind, team, line = pick
                    if kind == "spread":
                        is_home = side_is_home(team, home_name, away_name)
                        if is_home is None:
                            notes.append("Pick side could not be matched to home/away; Grade left Pending.")
                        else:
                            new["Grade"] = {"Won": "Win", "Lost": "Loss", "Push": "Push"}[
                                grade_spread_pick(margin, line, is_home)]
                            if close_spread is not None and f.get("Sharp-Sheet Closing Line") is None:
                                cpick = closing_pick_line(float(close_spread), is_home)
                                new["Sharp-Sheet Closing Line"] = cpick
                                new["Sharp-Sheet CLV Points"] = round(line - cpick, 2)
                    else:
                        new["Grade"] = {"Won": "Win", "Lost": "Loss", "Push": "Push"}[
                            grade_total_pick(hs + aw, line, team)]
                        if close_total is not None and f.get("Sharp-Sheet Closing Line") is None:
                            new["Sharp-Sheet Closing Line"] = float(close_total)
                            new["Sharp-Sheet CLV Points"] = round(
                                (float(close_total) - line) if team == "over" else (line - float(close_total)), 2)
                notes.append(f"Graded vs {used_close}." if close_spread is not None else "No line to grade against.")
                new["Status Notes"] = append_note(f.get("Status Notes"), " ".join(notes))
                ledger_patches.append({"id": r["id"], "fields": new})
                report.append(f"{f.get('Game')}: graded final {aw:g}-{hs:g} (away-home), margin {margin:+g}, "
                              f"{new.get('Spread Result')}/{new.get('O/U Result')}"
                              + (f", pick {new.get('Grade')}" if new.get("Grade") else ""))
                graded_margins[f"{es.norm(away_name)}@{es.norm(home_name)}"] = {
                    "away": aw, "home": hs, "margin": margin, "total": hs + aw,
                    "close_spread": close_spread, "close_total": close_total,
                    "home_name": home_name, "away_name": away_name,
                }

    # --- pool legs ---
    leg_patches, bet_patches = [], {}
    if graded_margins or True:  # backfill works from ledger rows even for past weeks
        legs = at_list_all(LEGS, token)
        ledger_all = at_list_all(LEDGER, token, "AND({Record Type}='Game')")
        idx = {}
        for r in ledger_all:
            f = r["fields"]
            if f.get("Home Score") is None:
                continue
            idx[f"{es.norm(f.get('Away Team',''))}@{es.norm(f.get('Home Team',''))}"] = {
                "away": f.get("Away Score"), "home": f.get("Home Score"),
                "margin": (f.get("Home Score") or 0) - (f.get("Away Score") or 0),
                "total": (f.get("Home Score") or 0) + (f.get("Away Score") or 0),
                "close_spread": f.get("Closing Spread (Home)"), "close_total": f.get("Over/Under Line"),
                "home_name": f.get("Home Team", ""), "away_name": f.get("Away Team", ""),
                "league": f.get("League", ""), "date": f.get("Date", ""),
            }
        for r in legs:
            f = r["fields"]
            g = (f.get("Game") or "")
            m = re.split(r"\s+(?:at|vs\.?)\s+", g, maxsplit=1)
            if len(m) != 2:
                continue
            a, h = es.norm(m[0]), es.norm(m[1])
            info = graded_margins.get(f"{a}@{h}") or idx.get(f"{a}@{h}") or graded_margins.get(f"{h}@{a}") or idx.get(f"{h}@{a}")
            if not info:
                continue
            flip = f"{h}@{a}" in graded_margins or f"{h}@{a}" in idx
            sel = (f.get("Selection") or "").strip()
            new: dict = {}
            if f.get("Final Score") is None:
                new["Final Score"] = f"{info['away']:g}-{info['home']:g}"
            market = (f.get("Market") or "").strip()
            mtotal = LEG_TOTAL_RE.match(sel)
            mspread = LEG_SPREAD_RE.match(sel)
            if mtotal:
                market = "Total"
            result = None
            if market == "Total" and mtotal:
                side, line = mtotal.group(1).lower(), float(mtotal.group(2))
                result = grade_total_pick(info["total"], line, side)
                if f.get("Line") is None:
                    new["Line"] = line
                if f.get("Closing Line") is None and info.get("close_total") is not None:
                    new["Closing Line"] = info["close_total"]
                    new["CLV Points"] = round((info["close_total"] - line) if side == "over" else (line - info["close_total"]), 2)
            elif market == "Spread" and mspread:
                team, line = mspread.group(1).strip(), float(mspread.group(2))
                is_home = side_is_home(team, info["home_name"], info["away_name"])
                if is_home is None:
                    continue
                margin = info["margin"] if not flip else -info["margin"]
                result = grade_spread_pick(margin, line, is_home)
                if f.get("Line") is None:
                    new["Line"] = line
                if f.get("Closing Line") is None and info.get("close_spread") is not None:
                    cpick = closing_pick_line(info["close_spread"] if not flip else -info["close_spread"], is_home)
                    new["Closing Line"] = cpick
                    new["CLV Points"] = round(line - cpick, 2)
            elif market == "Moneyline" or (not mtotal and not mspread):
                # selection is a team name; moneyline wins if that team wins outright
                is_home = side_is_home(sel, info["home_name"], info["away_name"])
                if is_home is None:
                    continue
                margin = info["margin"] if not flip else -info["margin"]
                result = "Won" if (margin > 0 if is_home else margin < 0) else ("Lost" if margin != 0 else "Push")
            if result and f.get("Result") in (None, "Pending"):
                new["Result"] = result
            if new:
                leg_patches.append({"id": r["id"], "fields": new})
                report.append(f"Leg '{sel}' ({g}): " + ", ".join(new.keys()))
            # settle parent bet
            if f.get("Bet"):
                for bet_id in f["Bet"]:
                    bet_patches.setdefault(bet_id, []).append(result or f.get("Result"))

    bet_settlements: list[dict] = []
    if bet_patches:
        bets = {b["id"]: b for b in at_list_all(BETS, token)}
        for bet_id, results in bet_patches.items():
            bet = bets.get(bet_id)
            if not bet or bet["fields"].get("Status") not in (None, "Pending"):
                continue
            if any(x is None or x == "Pending" for x in results) or len(results) != (bet["fields"].get("Leg Count") or len(results)):
                continue
            losses = [x for x in results if x == "Lost"]
            wins = [x for x in results if x == "Won"]
            units = float(bet["fields"].get("Units Wagered") or 0)
            new: dict = {}
            if losses:
                new["Status"], new["Net Units"] = "Lost", -units
            elif len(wins) == len(results):
                mult = (2 ** len(wins) - 1) if bet["fields"].get("Bet Type") == "Parlay" else 1
                new["Status"], new["Net Units"] = "Won", round(units * mult, 2)
            elif wins:
                # no losses, some pushes: pushed legs drop out (stake returned on those legs)
                if len(wins) == 1:
                    new["Status"], new["Net Units"] = "Won", round(units, 2)
                else:
                    new["Status"], new["Net Units"] = "Won", round(units * (2 ** len(wins) - 1), 2)
                new["Notes"] = append_note(bet["fields"].get("Notes"),
                                           f"Auto-graded: {len(results) - len(wins)} push leg(s) treated as removed.")
            else:
                new["Status"], new["Net Units"] = "Push", 0
            bet_settlements.append({"id": bet_id, "fields": new})
            report.append(f"Bet '{bet['fields'].get('Bet')}': settled {new['Status']} ({new['Net Units']:+g} u)")

    # --- Calibration Log upserts ---
    calib_rows = at_list_all(CALIB, token)
    by_run = {c["fields"].get("Run"): c for c in calib_rows}
    ledger_all = at_list_all(LEDGER, token, "AND({Record Type}='Game',{Sharp-Sheet Tier})")
    stats: dict[tuple, dict] = {}
    for r in ledger_all:
        f = r["fields"]
        if f.get("Grade") not in ("Win", "Loss", "Push"):
            continue
        wk = week_of(f.get("Date", ""), f.get("League", "NCAAF"))
        key = (f.get("League", "NCAAF"), wk, f.get("Sharp-Sheet Tier"))
        s = stats.setdefault(key, {"wins": 0, "losses": 0, "pushes": 0, "clv": [], "units": 0.0, "net": 0.0, "dates": []})
        g = f["Grade"]
        if g == "Win":
            s["wins"] += 1
        elif g == "Loss":
            s["losses"] += 1
        else:
            s["pushes"] += 1
        if f.get("Sharp-Sheet CLV Points") is not None:
            s["clv"].append(float(f["Sharp-Sheet CLV Points"]))
        u = float(f.get("Sharp-Sheet Suggested Units") or 0)
        s["units"] += u
        s["net"] += u * (1 if g == "Win" else (-1 if g == "Loss" else 0))
        s["dates"].append(f.get("Date", ""))
    calib_patches, calib_creates = [], []
    for (sport, wk, tier), s in sorted(stats.items()):
        graded = s["wins"] + s["losses"] + s["pushes"]
        run = f"{sport} Wk{wk} - Sharp-Sheet {tier}"
        fields = {
            "Picks Graded": graded, "Wins": s["wins"], "Losses": s["losses"], "Pushes": s["pushes"],
            "Hit Rate": (s["wins"] / graded) if graded else 0,
            "Avg CLV Points": round(sum(s["clv"]) / len(s["clv"]), 2) if s["clv"] else None,
            "Units Staked": round(s["units"], 2), "Net Units": round(s["net"], 2),
            "20+ Graded Picks": graded >= 20,
        }
        fields = {k: v for k, v in fields.items() if v is not None}
        if run in by_run:
            calib_patches.append({"id": by_run[run]["id"], "fields": fields})
        else:
            fields.update({"Run": run, "Sport": sport, "Week": wk, "Tier": tier,
                           "Date": min(s["dates"])[:10] if s["dates"] else None,
                           "Notes": "Auto-generated by close_grade sync."})
            calib_creates.append({"fields": fields})
        report.append(f"Calibration: {run}: {s['wins']}-{s['losses']}-{s['pushes']} net {s['net']:+g}")

    mode = "LIVE" if live else "DRY RUN"
    if live:
        at_write(token, ledger_patches)                    # ledger rows (closing + grading)
        at_write(token, bet_settlements, table=BETS)       # bet settlements
        at_write(token, leg_patches, table=LEGS)
        at_write(token, calib_patches, calib_creates, table=CALIB)
    lines = [f"Mode: {mode}", f"Ledger patches: {len(ledger_patches)}", f"Leg patches: {len(leg_patches)}",
             f"Calibration upserts: {len(calib_patches) + len(calib_creates)}"] + report[:80]
    print("\n".join(lines))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("## Close & grade\n\n" + "\n".join(f"- {x}" for x in lines) + "\n")


if __name__ == "__main__":
    main()
