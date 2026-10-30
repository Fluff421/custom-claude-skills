#!/usr/bin/env python3
"""NCAAF injury pull for the Signal Desk Ledger (no scraping API, no AI).

Fetches two public pages directly (Covers and DraftEdge), parses every team's entries, merges them
per upcoming NCAAF ledger game and writes ONLY the `Injury Notes` field.

Safety rules:
- Dry run by default (INJURY_PULL_LIVE=1 to write).
- Only NCAAF rows. Never touches Splash, picks, grades, or any field except `Injury Notes`.
- Only overwrites a blank note or one that starts with "[Injuries " (this job's own stamp or the
  earlier manual one). Any other hand-written note is left alone.
- Health gates: a source with too few teams/entries is treated as failed and left out of the note.
  If both fail nothing is written.
- Notes carry source update times, not fetch times, so unchanged data causes no Airtable writes.
- Blank is not healthy: a team with no entries is written as "none listed", which is not a clean bill.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import espn_sync as es  # noqa: E402

COVERS_URL = "https://www.covers.com/sport/football/ncaaf/injuries"
DRAFTEDGE_URL = "https://draftedge.com/cfb/college-football-injury-report/"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MIN_COVERS_TEAMS = 90
MIN_DRAFTEDGE_ENTRIES = 60
MAX_PER_TEAM = 12
STATUS_RANK = {"out": 0, "ir": 0, "doubtful": 1, "questionable": 2, "probable": 3}
STATUS_ABBR = {"out": "OUT", "ir": "IR", "doubtful": "D", "questionable": "Q", "probable": "P"}
OL = {"OL", "OT", "OG", "C", "T", "G", "IOL"}
LEDGER_DEFAULT = es.LEDGER_DEFAULT
LEDGER_ALIASES = {"olemiss": "mississippi", "ncstate": "northcarolinastate"}  # ledger name -> Covers school (normalized)
DE_ALIASES = {"miamihurricanes": "Miami (FL)", "ulmonroewarhawks": "Louisiana-Monroe", "olemissrebels": "Mississippi",
              "ncstatewolfpack": "North Carolina State", "westvirginamountaineers": "West Virginia",
              "westvirginiamountaineers": "West Virginia"}  # DraftEdge full name -> Covers school
WARNINGS: list[str] = []
UNRECOGNISED: set[str] = set()


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print("WARN:", msg, file=sys.stderr)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def status_key(text: str) -> str:
    t = text.lower()
    for k in ("out", "doubtful", "questionable", "probable"):
        if t.startswith(k):
            return k
    return "ir" if "injured reserve" in t or t.startswith("ir") else t.split(" ")[0]


# ---------- parsers ----------
def parse_covers(page: str) -> dict[str, list[dict]]:
    teams: dict[str, list[dict]] = {}
    for block in re.split(r'<a id="[^"]*"></a>\s*<section>', page)[1:]:
        m = re.search(r'covers-CoversMatchups-teamName">(.*?)</div>', block, re.S)
        if not m:
            continue
        name = clean(m.group(1).split("<br>")[0])  # school only, e.g. "Mississippi State"
        rows = []
        for tr in re.findall(r"<tr>\s*<td>\s*<span class='player-link'>(.*?)</tr>", block, re.S):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", "<td>" + tr, re.S)
            if len(cells) < 3:
                continue
            player, pos, st = clean(cells[0]), clean(cells[1]), cells[2]
            bold = re.search(r"<b>(.*?)</b>", st, re.S)
            label = clean(bold.group(1)) if bold else clean(st)
            date = re.search(r"\(\s*([^)]*?)\s*\)", re.sub(r"<b>.*?</b>", "", st, flags=re.S))
            status, _, injury = label.partition(" - ")
            rows.append({"player": player, "pos": pos, "status": status_key(status), "injury": injury.strip(),
                         "date": re.sub(r"^[A-Za-z]{3},\s*", "", date.group(1)) if date else "", "src": "C"})
        teams[name] = rows
    return teams


def canon_de(full: str, schools: list[str]) -> str | None:
    n = es.norm(full)
    if n in DE_ALIASES:
        return DE_ALIASES[n]
    hits = [sc for sc in schools if n.startswith(es.norm(sc))]
    return max(hits, key=len) if hits else None


def parse_draftedge(page: str, schools: list[str] | None = None) -> tuple[dict[str, list[dict]], str]:
    upd = re.search(r"updated-time\">\s*([^<]+?)\s*<", page)
    teams: dict[str, list[dict]] = {}
    for tr in re.findall(r'<tr data-status="[^"]*">(.*?)</tr>', page, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 5:
            continue
        name, pos, team = clean(tds[0]), clean(tds[1]), clean(tds[2])
        key = canon_de(team, schools) if schools else team
        if key is None:
            UNRECOGNISED.add(team)  # mostly FCS teams that are not in the ledger
            continue
        teams.setdefault(key, []).append({"player": name, "pos": pos, "status": status_key(clean(tds[3])),
                                           "injury": clean(tds[4]).replace("Undisclosed", "").strip(),
                                           "date": "", "src": "D"})
    return teams, (upd.group(1) if upd else "")


# ---------- matching ----------
def find_team(ledger_name: str, source: dict, ledger_names: set[str] | None = None) -> str | None:
    key = LEDGER_ALIASES.get(es.norm(ledger_name), es.norm(ledger_name))
    hits = [t for t in source if es.norm(t) == key]
    return hits[0] if hits else None


# ---------- merge / format ----------
def pos_rank(pos: str) -> int:
    return 0 if pos == "QB" else 1 if pos in OL else 2


def pkey(e: dict) -> str:
    parts = es.norm(e["player"].replace(".", " ")).split()
    n = re.sub(r"[^a-z]", "", e["player"].lower().split()[-1]) if e["player"].split() else ""
    return n + "|" + (e["player"].strip()[:1].lower())


def merge_team(entries: list[dict]) -> list[str]:
    by: dict[str, list[dict]] = {}
    for e in entries:
        by.setdefault(pkey(e), []).append(e)
    merged = []
    for group in by.values():
        d = next((e for e in group if e["src"] == "D"), None)
        c = next((e for e in group if e["src"] == "C"), None)
        main = d or c
        label = f"{main['player']} {main['pos']} {STATUS_ABBR.get(main['status'], main['status'].upper())}"
        inj = main["injury"] or (c or {}).get("injury", "")
        if inj:
            label += f" ({inj})"
        if d and c:
            label += " [both"
            label += f"; Covers {STATUS_ABBR.get(c['status'], c['status'])} {c['date']}]" if c["status"] != d["status"] else "]"
        elif c:
            label += f" [C {c['date']}]" if c["date"] else " [C]"
        else:
            label += " [D]"
        merged.append((STATUS_RANK.get(main["status"], 4), pos_rank(main["pos"]), label))
    merged.sort()
    out = [m[2] for m in merged[:MAX_PER_TEAM]]
    if len(merged) > MAX_PER_TEAM:
        out.append(f"+{len(merged) - MAX_PER_TEAM} more")
    return out


def build_note(away: str, home: str, cov, de, cov_ok: bool, de_ok: bool, ledger_names: set[str], de_stamp: str,
               cov_latest: str) -> tuple[str, list[str]]:
    miss = []
    parts = []
    for label, name in (("AWAY", away), ("HOME", home)):
        entries = []
        for ok, src in ((cov_ok, cov), (de_ok, de)):
            if ok:
                t = find_team(name, src, ledger_names)
                if t is None:
                    if src is cov:  # Covers lists every team (even with none); a miss means a naming problem
                        miss.append(f"{name} not matched in Covers")
                else:
                    entries += src[t]
        parts.append(f"{label} {name}: " + ("; ".join(merge_team(entries)) if entries else "none listed (not a clean bill)"))
    used = [s for s, ok in (("Covers (latest entry " + cov_latest + ")", cov_ok), ("DraftEdge (updated " + de_stamp + ")", de_ok)) if ok]
    down = [s for s, ok in (("Covers", cov_ok), ("DraftEdge", de_ok)) if not ok]
    head = "[Injuries AUTO | SECONDARY, unverified] " + " + ".join(used)
    if down:
        head += f". UNAVAILABLE: {', '.join(down)}"
    head += ". C=Covers, D=DraftEdge, dates are Covers entry dates. Blank is not healthy."
    return head + " " + " | ".join(parts), miss


def main() -> None:
    token = os.environ.get("AIRTABLE_TOKEN", "").strip()
    base = os.environ.get("AIRTABLE_BASE_ID", "").strip()
    table = os.environ.get("LEDGER_TABLE_ID", "").strip() or LEDGER_DEFAULT
    live = os.environ.get("INJURY_PULL_LIVE", "0").strip() == "1"
    if not (token and base):
        raise SystemExit("ERROR: AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.")
    cov, de, de_stamp, cov_ok, de_ok = {}, {}, "", False, False
    try:
        cov = parse_covers(fetch(COVERS_URL))
        cov_ok = len(cov) >= MIN_COVERS_TEAMS
        if not cov_ok:
            warn(f"Covers parsed only {len(cov)} teams (< {MIN_COVERS_TEAMS}); page format may have changed.")
    except Exception as exc:  # noqa: BLE001
        warn(f"Covers fetch/parse failed: {exc}")
    try:
        de, de_stamp = parse_draftedge(fetch(DRAFTEDGE_URL), list(cov) if cov_ok else None)
        n = sum(len(v) for v in de.values())
        de_ok = n >= MIN_DRAFTEDGE_ENTRIES and bool(de_stamp)
        if not de_ok:
            warn(f"DraftEdge parsed {n} entries / stamp '{de_stamp}'; treated as failed.")
    except Exception as exc:  # noqa: BLE001
        warn(f"DraftEdge fetch/parse failed: {exc}")
    cov_latest = ""
    if cov_ok:
        yr = dt.date.today().year
        ds = []
        for rows in cov.values():
            for r in rows:
                try:
                    ds.append(dt.datetime.strptime(f"{r['date']} {yr}", "%b %d %Y").date())
                except ValueError:
                    pass
        cov_latest = max(ds).strftime("%b %d") if ds else "unknown"
    rows = [r for r in es.at_list(base, table, token) if r["fields"].get("League") == "NCAAF"]
    ledger_names = {r["fields"].get(k, "") for r in rows for k in ("Home Team", "Away Team")} - {""}
    updates, report, skipped = [], [], []
    if not (cov_ok or de_ok):
        warn("Both sources unavailable; nothing written.")
        rows = []
    for r in rows:
        f = r["fields"]
        note, miss = build_note(f.get("Away Team", ""), f.get("Home Team", ""), cov, de, cov_ok, de_ok, ledger_names,
                                de_stamp, cov_latest)
        for m in miss:
            warn(f"{f.get('Game')}: {m}")
        cur = (f.get("Injury Notes") or "").strip()
        if cur and not cur.startswith("[Injuries "):
            skipped.append(f"{f.get('Game')} (hand-written note kept)")
            continue
        if cur != note:
            updates.append({"id": r["id"], "fields": {"Injury Notes": note}})
            report.append(f"{f.get('Game')}: note updated")
    if live and updates:
        es.at_patch(base, table, token, updates)
    if UNRECOGNISED:
        print(f"Note: {len(UNRECOGNISED)} DraftEdge teams not in Covers list (mostly FCS): " + ", ".join(sorted(UNRECOGNISED))[:300])
    lines = [f"Mode: {'LIVE' if live else 'DRY RUN'}",
             f"Covers: {'ok' if cov_ok else 'FAILED'} ({len(cov)} teams, latest entry {cov_latest or 'n/a'})",
             f"DraftEdge: {'ok' if de_ok else 'FAILED'} ({sum(len(v) for v in de.values())} entries, updated {de_stamp or 'n/a'})",
             f"NCAAF ledger rows scanned: {len(rows)}", f"Notes to write: {len(updates)}"]
    lines += [f"Skipped: {s}" for s in skipped] + [f"WARNING: {w}" for w in WARNINGS] + report[:60]
    print("\n".join(lines))
    if updates:
        print("\nSample note:\n" + updates[0]["fields"]["Injury Notes"])
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("## NCAAF injury pull\n\n" + "\n".join(f"- {x}" for x in lines) + "\n")
    out = os.environ.get("INJURY_SNAPSHOT_PATH")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"covers": cov, "draftedge": de, "draftedge_updated": de_stamp}, fh)
    if WARNINGS and not (cov_ok or de_ok):
        sys.exit(1)


if __name__ == "__main__":
    main()
