#!/usr/bin/env python3
"""
grill_plan.py — deterministic cook-plan generator bundled with the
PitMaster AI Claude Skill.

This is the offline-first core of the original PitMaster AI project,
trimmed down for the Skill environment: no LangChain, no live web
retrieval, no Streamlit — just correct temps/times/timelines computed
from data/grill_db.json (relative to this script), formatted as
markdown. Claude runs this via code execution when the skill triggers,
then presents the output — adding its own conversational framing or
freeform notes (e.g. "since it's bone-in, expect a few extra minutes")
around the numbers, but never overriding the numbers themselves.

Usage:
    python grill_plan.py "ribeye"
    python grill_plan.py "pulled pork" --grill traeger
    python grill_plan.py --list
    python grill_plan.py --pantry "shrimp, corn, ribeye"
    python grill_plan.py --dual "baby back ribs:traeger,corn:blackstone" --dish-name "Game Day Spread"
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "grill_db.json"


def load_db() -> dict:
    with open(DB_PATH) as f:
        return json.load(f)


def _all_item_keys(db: dict) -> list[str]:
    return [key for category in db.values() for key in category]


_STOPWORDS = {"a", "an", "the", "is", "that", "in", "of", "with", "on", "and",
              "thick", "inches", "inch", "oz", "lb", "lbs", "pound", "pounds", "bone"}


def _tokenize(text: str) -> set[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords, naive singularize."""
    raw = [w for w in "".join(c if c.isalnum() else " " for c in text.lower()).split()]
    tokens = set()
    for w in raw:
        if w in _STOPWORDS:
            continue
        tokens.add(w[:-1] if w.endswith("s") and len(w) > 3 else w)
    return tokens


def find_item(query: str, db: dict) -> Optional[tuple[str, str, dict]]:
    """
    Match free text against GRILL_DB keys.
    """
    normalized = query.lower().strip().replace(" ", "_").replace("-", "_")
    keys = _all_item_keys(db)

    if normalized in keys:
        for category, items in db.items():
            if normalized in items:
                return category, normalized, items[normalized]

    close = difflib.get_close_matches(normalized, keys, n=1, cutoff=0.85)
    if close:
        matched_key = close[0]
        for category, items in db.items():
            if matched_key in items:
                return category, matched_key, items[matched_key]

    query_tokens = _tokenize(query)
    if not query_tokens:
        return None

    candidates = []
    for category, items in db.items():
        for key, entry in items.items():
            key_tokens = _tokenize(key.replace("_", " "))
            if not key_tokens:
                continue
            if key_tokens.issubset(query_tokens) or query_tokens.issubset(key_tokens):
                overlap = len(key_tokens & query_tokens)
                candidates.append((overlap, category, key, entry))

    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    _, category, key, entry = candidates[0]
    return category, key, entry


@dataclass
class CookPlan:
    dish_name: str
    grill_assignment: str
    difficulty: str
    total_time: str
    traeger_settings: Optional[dict] = None
    blackstone_settings: Optional[dict] = None
    timeline: list[str] = field(default_factory=list)
    pro_tips: list[str] = field(default_factory=list)
    recipe_sources: list[str] = field(default_factory=list)


def _difficulty_for(entry: dict) -> str:
    if entry.get("reverse_sear"):
        return "Intermediate"
    if entry["category"] in ("beef", "pork") and entry.get("traeger") and "hour" in str(entry["traeger"].get("cook_time", "")):
        return "Intermediate"
    return "Easy"


def plan_single_grill(item_key: str, entry: dict, grill: str, dish_name: Optional[str] = None) -> CookPlan:
    grill = grill.lower()
    dish_name = dish_name or item_key.replace("_", " ").title()
    plan = CookPlan(
        dish_name=dish_name,
        grill_assignment="Traeger" if grill == "traeger" else "Blackstone",
        difficulty=_difficulty_for(entry),
        total_time="",
        pro_tips=[entry.get("notes", "")] if entry.get("notes") else [],
    )
    if grill == "traeger" and entry.get("traeger"):
        t = entry["traeger"]
        plan.traeger_settings = {
            "Preheat Temp": f"{t['preheat_temp_f']}\u00b0F",
            "Pellet Recommendation": t.get("pellet", "Any"),
            "Super Smoke": "On" if t.get("super_smoke") else "Off",
            "Cook Temp": f"{t['cook_temp_f']}\u00b0F",
            "Cook Time": t.get("cook_time", "N/A"),
            "Internal Target": f"{t.get('internal_target_f', entry.get('chef_preferred_temp_f', 'N/A'))}\u00b0F",
            "Rest Time": f"{entry.get('rest_time_min', 0)} min",
        }
        plan.total_time = t.get("cook_time", "N/A")
    elif grill == "blackstone" and entry.get("blackstone"):
        b = entry["blackstone"]
        plan.blackstone_settings = {
            "Preheat Time": f"{b['preheat_time_min']} min",
            "Heat Zone": b.get("heat_zone", "Medium"),
            "Oil Recommendation": b.get("oil", "Avocado oil"),
            "Cook Time per side": b.get("cook_time_per_side", "N/A"),
            "Internal Target or Visual Cue": b.get("internal_target_or_cue", "N/A"),
        }
        plan.total_time = b.get("cook_time_per_side", "N/A")
    else:
        raise ValueError(f"'{item_key}' has no {grill} method in GRILL_DB.")
    plan.recipe_sources = _default_sources_for(entry, grill)
    return plan


def plan_reverse_sear(item_key: str, entry: dict, dish_name: Optional[str] = None) -> CookPlan:
    if not entry.get("reverse_sear"):
        raise ValueError(f"'{item_key}' is not flagged for reverse sear in GRILL_DB.")
    if not (entry.get("traeger") and entry.get("blackstone")):
        raise ValueError(f"'{item_key}' is missing Traeger or Blackstone data needed for reverse sear.")

    t, b = entry["traeger"], entry["blackstone"]
    dish_name = dish_name or f"Reverse-Seared {item_key.replace('_', ' ').title()}"
    rest = entry.get("rest_time_min", 8)

    plan = CookPlan(
        dish_name=dish_name,
        grill_assignment="Both",
        difficulty="Intermediate",
        total_time=f"~{t.get('cook_time', 'varies')} smoke + sear + {rest} min rest",
        traeger_settings={
            "Preheat Temp": f"{t['preheat_temp_f']}\u00b0F",
            "Pellet Recommendation": t.get("pellet", "Any"),
            "Super Smoke": "On" if t.get("super_smoke") else "Off",
            "Cook Temp": f"{t['cook_temp_f']}\u00b0F",
            "Cook Time": t.get("cook_time", "N/A"),
            "Internal Target": f"Pull at {t.get('internal_target_f', 'N/A')}\u00b0F for the sear",
            "Rest Time": "N/A — goes straight to sear",
        },
        blackstone_settings={
            "Preheat Time": f"{b['preheat_time_min']} min (get it ripping hot before Phase 1 finishes)",
            "Heat Zone": "Ripping Hot",
            "Oil Recommendation": b.get("oil", "Avocado oil"),
            "Cook Time per side": b.get("cook_time_per_side", "2-3 min"),
            "Internal Target or Visual Cue": b.get("internal_target_or_cue", "Deep crust, pull to chef-preferred temp"),
        },
        timeline=[
            "T-0:00 — Start Traeger, begin smoke phase",
            f"T-varies — Pull at {t.get('internal_target_f', 'target')}\u00b0F, griddle should already be ripping hot",
            f"T+0:00 — Sear {b.get('cook_time_per_side', '2-3 min')} per side on Blackstone",
            f"T+sear — Rest {rest} min, tented loosely with foil",
            "T+rest — Slice and serve",
        ],
        pro_tips=[p for p in [
            entry.get("notes", ""),
            "Get the griddle ripping hot BEFORE the smoke phase finishes — the handoff should be immediate.",
            "Tent loosely, not tightly — a tight foil wrap steams the crust you just built.",
        ] if p],
        recipe_sources=_default_sources_for(entry, "both"),
    )
    return plan


def plan_dual_grill(items: list[tuple[str, dict, str]], dish_name: str = "Dual-Grill Cook") -> CookPlan:
    def _minutes_estimate(entry: dict, grill: str) -> int:
        source = entry.get(grill) or {}
        raw = source.get("cook_time") or source.get("cook_time_per_side") or ""
        digits = "".join(c if c.isdigit() else " " for c in raw).split()
        return max((int(d) for d in digits), default=15)

    enriched = [(k, e, g, _minutes_estimate(e, g)) for k, e, g in items]
    enriched.sort(key=lambda x: x[3], reverse=True)
    anchor_minutes = enriched[0][3] if enriched else 0

    timeline = [f"T-0:00 — Start {enriched[0][0].replace('_', ' ').title()} on {enriched[0][2].title()} (longest item, sets the pace)"]
    for k, e, g, minutes in enriched[1:]:
        start_offset = max(anchor_minutes - minutes, 0)
        timeline.append(f"T+{start_offset}:00 — Start {k.replace('_', ' ').title()} on {g.title()}")
    timeline.append(f"T+{anchor_minutes}:00 — Everything should be finishing — pull, rest as needed, and plate")

    return CookPlan(
        dish_name=dish_name, grill_assignment="Both", difficulty="Intermediate",
        total_time=f"~{anchor_minutes} min total", timeline=timeline,
        pro_tips=[
            "The longest-cooking item sets the schedule — everything else is staggered backward from its finish time.",
            "Double-check both grills' actual progress against the timeline; smoker times drift with weather and lid-opening.",
        ],
    )


def _default_sources_for(entry: dict, grill: str) -> list[str]:
    sources = []
    if grill in ("traeger", "both") and entry.get("traeger"):
        sources.append("https://www.traeger.com/recipes")
    if grill in ("blackstone", "both") and entry.get("blackstone"):
        sources.append("https://blackstoneproducts.com/blogs/recipes")
    sources.append("https://amazingribs.com")
    return sources


def format_cook_plan(plan: CookPlan) -> str:
    lines = [
        f"### \U0001f525 Cook Plan: {plan.dish_name}",
        f"**Grill Assignment:** {plan.grill_assignment}",
        f"**Difficulty:** {plan.difficulty}",
        f"**Total Time:** {plan.total_time}",
        "\n---",
    ]
    if plan.traeger_settings:
        lines.append("**TRAEGER SETTINGS**")
        lines += [f"- {k}: {v}" for k, v in plan.traeger_settings.items()]
        lines.append("\n---")
    if plan.blackstone_settings:
        lines.append("**BLACKSTONE SETTINGS**")
        lines += [f"- {k}: {v}" for k, v in plan.blackstone_settings.items()]
        lines.append("\n---")
    if plan.timeline:
        lines.append("**TIMELINE**")
        lines += [f"- {step}" for step in plan.timeline]
        lines.append("\n---")
    if plan.pro_tips:
        lines.append("**PRO TIPS**")
        lines += [f"- {tip}" for tip in plan.pro_tips]
        lines.append("\n---")
    if plan.recipe_sources:
        lines.append("**RECIPE SOURCES**")
        lines += [f"- {src}" for src in plan.recipe_sources]
    return "\n".join(lines)


def what_can_i_cook(ingredients: list[str], db: dict) -> list[dict]:
    matches = []
    for ing in ingredients:
        found = find_item(ing, db)
        if found:
            category, key, entry = found
            matches.append({"ingredient": ing, "matched_item": key, "category": category, "entry": entry})

    def _sort_weight(m: dict) -> int:
        t = m["entry"].get("traeger", {}) or {}
        return 100 if "hour" in str(t.get("cook_time", "")) else 10

    matches.sort(key=_sort_weight, reverse=True)
    return matches


def print_list(db: dict) -> None:
    for category, items in db.items():
        print(f"{category}:")
        for key, entry in items.items():
            rs = " [reverse-sear]" if entry.get("reverse_sear") else ""
            print(f"  - {key}{rs}")


def main() -> None:
    parser = argparse.ArgumentParser(description="PitMaster AI deterministic cook-plan generator")
    parser.add_argument("item", nargs="?", help="Item name (use --list to see exact valid keys)")
    parser.add_argument("--grill", choices=["traeger", "blackstone"], help="Force a specific grill")
    parser.add_argument("--list", action="store_true", help="List every valid GRILL_DB item key")
    parser.add_argument("--pantry", help="Comma-separated ingredient list for a ranked meal plan")
    parser.add_argument("--dual", help="Comma-separated item:grill pairs, e.g. 'ribs:traeger,corn:blackstone'")
    parser.add_argument("--dish-name", default=None, help="Optional display name for --dual plans")
    args = parser.parse_args()

    db = load_db()

    if args.list:
        print_list(db)
        return

    if args.pantry:
        ingredients = [i.strip() for i in args.pantry.split(",") if i.strip()]
        matches = what_can_i_cook(ingredients, db)
        if not matches:
            print("No matches found in GRILL_DB for those ingredients.")
            return
        print(f"### \U0001f9ca What You Can Cook ({len(matches)} matches, longest cook first)\n")
        for m in matches:
            entry = m["entry"]
            grills = [g for g, k in (("Traeger", "traeger"), ("Blackstone", "blackstone")) if entry.get(k)]
            print(f"**{m['matched_item'].replace('_', ' ').title()}** ({' + '.join(grills)})")
            print(f"- {entry.get('notes', '')}")
            print()
        return

    if args.dual:
        pairs = []
        for chunk in args.dual.split(","):
            if ":" not in chunk:
                continue
            name, grill = chunk.split(":", 1)
            found = find_item(name.strip(), db)
            if found:
                _, key, entry = found
                pairs.append((key, entry, grill.strip().lower()))
        if not pairs:
            print("Couldn't match any --dual items in GRILL_DB.", file=sys.stderr)
            sys.exit(1)
        plan = plan_dual_grill(pairs, dish_name=args.dish_name or "Dual-Grill Cook")
        print(format_cook_plan(plan))
        return

    if not args.item:
        parser.print_help()
        sys.exit(1)

    found = find_item(args.item, db)
    if not found:
        print(f"'{args.item}' not found in GRILL_DB. Run with --list to see valid item keys.", file=sys.stderr)
        sys.exit(1)

    _, key, entry = found
    if entry.get("reverse_sear") and args.grill is None:
        plan = plan_reverse_sear(key, entry)
    elif args.grill:
        plan = plan_single_grill(key, entry, args.grill)
    elif entry.get("traeger"):
        plan = plan_single_grill(key, entry, "traeger")
    elif entry.get("blackstone"):
        plan = plan_single_grill(key, entry, "blackstone")
    else:
        print(f"'{key}' has no defined grill method. Notes: {entry.get('notes')}", file=sys.stderr)
        sys.exit(1)

    print(format_cook_plan(plan))


if __name__ == "__main__":
    main()
