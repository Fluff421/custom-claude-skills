# Injury and availability sources

Last reviewed: 2026-10-30. Update this file whenever a source or workflow changes.

| Source | League | Type | How we get it | Freshness | Trust |
|---|---|---|---|---|---|
| NFL.com official injury report, https://www.nfl.com/injuries/ | NFL | Official | Parsed from page HTML (`research/tools/nfl_injuries_snapshot.py` on the `research/grok-feed` branch); Grok writes per-team files there | Updates through the week; game status appears late | High. A blank Injuries column is not healthy; only "No Injuries Reported" means none |
| ESPN site API injuries | NFL | Aggregated | `espn_sync.py`, every 3 h, into the ledger `Injury Notes` | Every sync | Medium. "none listed" is not proof of health |
| Covers NCAAF injury report, https://www.covers.com/sport/football/ncaaf/injuries | NCAAF | Secondary aggregator | Manual: Gemini in Chrome extracts the page; the owner reformats it to compact markdown (Player / POS / Status / Injury / Report date per team) small enough to upload to chat | Each entry has its own report date. The 2026-10-30 export had nothing newer than Oct 21 | Low to medium. Stale; keep entry dates when quoting |
| DraftEdge NCAAF injury report, https://draftedge.com/cfb/college-football-injury-report/ | NCAAF | Secondary aggregator | Manual: same Chrome Gemini extraction, pasted as text | Page stamped "Last Updated" (2026-10-30 8:55 AM) | Medium. Fresher than Covers but many teams missing and many "Undisclosed" |
| Official conference availability reports | NCAAF | Official | Checked Wed to Sat; usually late in the week | Late week | High when published |

## Rules
- NCAAF has no machine-readable league-wide injury feed. NCAAF injury notes in the ledger are manual and secondary until official reports are ingested.
- Blank or "none listed" is never evidence of health.
- When sources disagree, prefer the newer dated one and say so. On 2026-10-30 they disagreed on Mississippi State QB Taylor (Covers Questionable Oct 17, DraftEdge OUT) and Syracuse QB Odom (Covers Questionable, DraftEdge OUT).
- Ledger notes from these sources start with "[Injuries <date> | SECONDARY, manual, unverified]" so they are distinguishable from automated ESPN notes.
- Manual workflow: open the page in Chrome, have Gemini in Chrome extract every team, reformat to the compact layout, attach in chat with the source URL and report date.
