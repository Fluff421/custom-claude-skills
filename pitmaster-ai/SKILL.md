---
name: pitmaster-ai
description: Generates a Traeger + Blackstone cook plan (temps, times, targets, rest, reverse-sear steps) for a named food item. Use when asked what/how to grill or when PitMaster AI is named.
---

# PitMaster AI

Dual-grill cooking intelligence for a Traeger pellet grill + Blackstone flat
top griddle. Produces correct preheat/cook temps, cook times, internal
temperature targets, rest times, and (for the right cuts) an automatic
reverse-sear workflow — grounded in a fixed reference database, not guessed.

## How to run this skill

The temps and times in `data/grill_db.json` are the ground truth. Never
invent or adjust a number yourself — always get it from the script below.

1. **List valid items** (do this first, every time — don't guess a key name):
   ```
   python scripts/grill_plan.py --list
   ```
   This prints every valid item, grouped by category, with `[reverse-sear]`
   flagged where it applies.

2. **Match the user's request to the closest listed item yourself.** Users
   describe food in natural language ("a bone-in pork chop, two inches
   thick," "some chicken thighs for the game"); the list gives you exact
   keys like `chops_thick_cut` or `thighs`. Pick the closest sensible match
   using your own judgment — don't pass the raw sentence to the script.

3. **Run the plan** with the exact key you picked:
   ```
   python scripts/grill_plan.py "chops_thick_cut"
   ```
   Add `--grill traeger` or `--grill blackstone` only if the user asked for
   a specific grill. Otherwise leave it off — items flagged `[reverse-sear]`
   automatically get the full smoke-then-sear workflow, which is usually
   what's wanted for steaks, chops, and similar cuts.

4. **Present the script's output as-is.** It's already formatted. You may
   add a short note around it (e.g. "since it's bone-in and extra-thick,
   lean toward the long end of that time range and check with a
   thermometer") but never edit the temps, times, or targets themselves.

5. **For "what can I cook" / pantry questions**, use:
   ```
   python scripts/grill_plan.py --pantry "shrimp, corn, ribeye"
   ```

6. **For coordinating multiple items across both grills at once**, use:
   ```
   python scripts/grill_plan.py --dual "baby back ribs:traeger,corn:blackstone" --dish-name "Game Day Spread"
   ```

7. **If nothing in `--list` is a reasonable match**, say so plainly and ask
   what the user actually has — don't fabricate a plan for an item that
   isn't in the data.

## Examples

**User:** "I've got a bone-in pork chop, about two inches thick — what's
the move on the Traeger and Blackstone?"
**Do:** Run `--list`, notice `chops_thick_cut [reverse-sear]` under pork,
run `python scripts/grill_plan.py "chops_thick_cut"`, present the result,
optionally add a one-line note about the extra thickness.

**User:** "What can I make with shrimp, corn, and a ribeye I have in the
fridge?"
**Do:** Run `python scripts/grill_plan.py --pantry "shrimp, corn, ribeye"`
and present the result.

**User:** "Running ribs on the Traeger and corn + burgers on the Blackstone
for the game — help me time it out."
**Do:** Run `python scripts/grill_plan.py --dual "baby back ribs:traeger,corn:blackstone,burgers:blackstone" --dish-name "Game Day Spread"`.

## What this skill does not do

- No live web lookups — it's offline reference data only, covering beef,
  pork, poultry, seafood, game, vegetables, and breakfast items across
  ~44 entries.
- No memory of past cook sessions between conversations.
- Won't produce a plan for anything not in the data — food safety numbers
  need to come from somewhere real, not a guess.
