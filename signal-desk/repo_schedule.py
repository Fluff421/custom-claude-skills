"""Owner-source game references, not Airtable rows or independent schedule verification.

Only a validated File 1 import can establish a new reference. State is staged in
memory and committed with the accepted import, never during planning/dry runs.
Read-only Ledger bindings preserve the repository identity and original quote.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

SCHEMA = "signal-desk.repo-schedule.v1"
PREFIX = "repo-game:"


def empty():
    return {"schema": SCHEMA, "games": []}


def load(path):
    return json.loads(path.read_text()) if path.exists() else empty()


class RepositorySchedule:
    def __init__(self, state, ledger, matcher, *, dump=None, digest=None):
        if not isinstance(state, dict) or state.get("schema") != SCHEMA or not isinstance(state.get("games"), list):
            raise ValueError("invalid repository schedule")
        self.state = copy.deepcopy(state)
        self.ledger = ledger
        self.matcher = matcher
        self.dump = dump
        self.digest = digest
        self.resolved = {}
        seen = set()
        for r in self.state["games"]:
            rid = r.get("reference_id")
            if not isinstance(rid, str) or not rid.startswith(PREFIX) or rid in seen:
                raise ValueError("invalid or duplicate repository reference identity")
            seen.add(rid)
            if not all(r.get(k) for k in ("league", "date_central", "away_team", "home_team", "kickoff_central", "first_source", "captures")):
                raise ValueError("incomplete repository schedule provenance")
            if self.identity(r["league"], r["date_central"], r["away_team"], r["home_team"]) != rid:
                raise ValueError("repository reference identity does not match its source")

    @staticmethod
    def identity(league, date, away, home):
        # Match normalization is the same as the existing importer; source names
        # and the initial date are retained, not rewritten on later observations.
        from splash_lines import norm
        key = [league, date, norm(away), norm(home)]
        return PREFIX + hashlib.sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest()[:24]

    def _try(self, g, candidates):
        try:
            return self.matcher(g, candidates)
        except ValueError as exc:
            # Only a genuine zero match permits a fallback. Ambiguity, reversed
            # orientation, malformed dates and other validation errors propagate.
            if "matches 0 Ledger rows; no rows created" in str(exc):
                return None
            raise

    def _source(self, g):
        return {"date_code": self.dump["date_code"], "input_sha256": self.digest,
                "extracted_at_utc": self.dump["extracted_at_utc"],
                "kickoff_central": g["kickoff_central"],
                "away_team": g["away_team"], "home_team": g["home_team"]}

    def _fields(self, r, ledger=None):
        # Imported first quote remains distinct from any later Ledger baseline.
        f = dict(ledger or {})
        f.update({"_id": r["reference_id"], "League": r["league"],
                  "Date": r["kickoff_central"][:10],
                  "Away Team": (ledger or {}).get("Away Team", r.get("display_away_team", r["away_team"])),
                  "Home Team": (ledger or {}).get("Home Team", r.get("display_home_team", r["home_team"])),
                  "Vegas Implied Home Margin": r["early_home_margin"],
                  "Over/Under Line": r["early_total"],
                  "_reference_origin": "repository",
                  "_ledger_record_id": (ledger or {}).get("_id"),
                  "_model_status": "unpriced"})
        f["Game"] = f"{f['Away Team']} @ {f['Home Team']}"
        if ledger and all(isinstance(ledger.get(k), (int, float))
                          and not isinstance(ledger[k], bool) and math.isfinite(ledger[k])
                          for k in ("Home FPI", "Away FPI")):
            f["_model_status"] = "available"
        return f

    def _repository_match(self, g):
        views = [self._fields(r) for r in self.state["games"]]
        hit = self._try(g, views)
        if hit:
            return hit
        # File 1 often supplies a school/nickname and File 2 a longer full name.
        # Allow an owner-supplied expansion only through the SAME unique dated,
        # both-team matcher. No global alias table or invented expansion.
        from splash_compare import _words
        aliases = copy.deepcopy(views)
        for f in aliases:
            for field in ("Away Team", "Home Team"):
                old = _words(f.get(field, ""))
                supplied = [g[k] for k in ("away_team", "home_team")
                            if old and old < _words(g.get(k, ""))]
                if len(supplied) == 1:
                    f[field] = supplied[0]
        return self._try(g, aliases)

    def resolve(self, g, _unused=None):
        rows = self.state["games"]
        hit = self._repository_match(g)
        ledger = self._try(g, self.ledger)
        if hit:
            r = next(r for r in rows if r["reference_id"] == hit["_id"])
            old_binding = r.get("ledger_record_id")
            if ledger and old_binding and old_binding != ledger["_id"]:
                raise ValueError("repository game has a conflicting Ledger binding")
            if ledger:
                r["ledger_record_id"] = ledger["_id"]
            if not ledger and self.dump:
                from splash_compare import _words
                changed = False
                for source_key, field in (("away_team", "display_away_team"), ("home_team", "display_home_team")):
                    old = r.get(field, r[source_key])
                    if _words(old) < _words(g[source_key]):
                        r[field] = g[source_key]
                        changed = True
                if changed:
                    r.setdefault("name_observations", []).append(self._source(g))
        elif ledger:
            self.resolved[ledger["_id"]] = ledger
            return ledger
        else:
            if not self.dump or self.dump.get("schema") != "signal-desk.splash-lines.v1":
                raise ValueError("no existing Ledger or repository schedule game; submit validated File 1 first")
            if g.get("home_away_certain") is not True:
                raise ValueError("new repository reference requires explicit certain home/away orientation")
            r = {"reference_id": self.identity(g["league"], g["kickoff_central"][:10],
                                               g["away_team"], g["home_team"]),
                 "league": g["league"], "date_central": g["kickoff_central"][:10],
                 "away_team": g["away_team"], "home_team": g["home_team"],
                 "kickoff_central": g["kickoff_central"],
                 "early_home_margin": -float(g["home_spread"]), "early_total": float(g["total"]),
                 "first_source": self._source(g), "captures": [],
                 "ledger_record_id": None}
            rows.append(r)
        if self.dump and self.dump.get("schema") == "signal-desk.splash-lines.v1":
            source = self._source(g)
            captures = r["captures"]
            existing = [c for c in captures if c["date_code"] == source["date_code"]]
            if existing and existing[0] != source:
                raise ValueError("repository schedule source identity changed")
            if not existing:
                from datetime import datetime
                when = lambda s: datetime.fromisoformat(s["extracted_at_utc"].replace("Z", "+00:00"))
                if captures and when(source) < max(when(c) for c in captures):
                    raise ValueError("repository captures must be chronological; no baseline rewrite")
                captures.append(source)
                r["kickoff_central"] = g["kickoff_central"]
        f = self._fields(r, ledger)
        self.resolved[f["_id"]] = f
        return f

    def games(self):
        out = {f["_id"]: f for f in self.ledger}
        for r in self.state["games"]:
            g = {"league": r["league"], "kickoff_central": r["kickoff_central"],
                 "away_team": r["away_team"], "home_team": r["home_team"],
                 "home_away_certain": True}
            ledger = self._try(g, self.ledger)
            if ledger and r.get("ledger_record_id") not in (None, ledger["_id"]):
                raise ValueError("repository game has a conflicting Ledger binding")
            if ledger:
                r["ledger_record_id"] = ledger["_id"]
            out[r["reference_id"]] = self._fields(r, ledger)
        out.update(self.resolved)
        return list(out.values())

    def match_details(self, ids):
        byid = {f["_id"]: f for f in self.games()}
        return [{"reference_id": rid,
                 "reference_origin": byid[rid].get("_reference_origin", "airtable"),
                 "ledger_record_id": byid[rid].get("_ledger_record_id")
                     if rid.startswith(PREFIX) else rid,
                 "model_status": byid[rid].get("_model_status", "existing-ledger")}
                for rid in ids]
