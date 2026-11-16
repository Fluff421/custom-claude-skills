# File 2: Splash Sports pick extraction

Version 2026-11-16. Owner-run extraction for the Pending/Open page or the Completed/History page, one page type per file. It works in Gemini in Chrome (side panel) or in Perplexity Computer's browser. It preserves source observations without authorizing betting, publication, result correction or Airtable writes. Check the output with [`splash_preflight.py`](splash_preflight.py) before submitting (see [CHAT_PROMPTS.md](CHAT_PROMPTS.md)).

## Why this version exists

The 2026-11-16 capture `SPL-C-20261116-1341` was rejected. Its one warning blocked import first, but three more defects sat behind it that no owner review can repair:

| Defect in the dump | Root cause in the old prompt |
|---|---|
| `kickoff_tz: "EST"` on all 41 legs (importer accepts only CST, CDT or null) | "Capture kickoff date/time and source timezone" with no separate field, so the source zone landed in `kickoff_tz` |
| Every `kickoff_as_shown` held the ticket's timestamp, e.g. "Sun, Nov 15, 11:33 PM EST" on Steelers at Bengals | No rule against copying a ticket-level time into a leg field |
| Ticket times labelled "placed" were after the games finished (likely settlement times) | No field for the ticket time's own label; `placed_at_central` was filled from an unlabeled time |
| Ole Miss at Oklahoma dated Sunday Nov 15 (Ledger: Saturday Nov 14) | Game dates were taken from the history page's day headers, which group by settlement |
| Tulane moneyline with `price: null` and no warning | No instruction to open the ticket detail for the price, or to warn when it is missing |

## Owner steps

1. Open Splash, choose Pending/Open or Completed/History, and set the range (completed: at least the last 7 days).
2. Expand every ticket and every leg. Open a ticket's detail view when a leg's kickoff, date or moneyline price is not on the summary row.
3. Paste the complete prompt below. If the reply starts with `STOP:`, fix what it names and run it again.
4. Save only the returned JSON, named exactly `<date_code>.json`, and run the preflight. Fix every ERROR by re-extracting, never by hand-editing.
5. Submit pending captures within 12 hours and completed captures within 24 hours (preferably within 4).

```text
TASK: Extract my Splash Sports tickets into ONE JSON object for Signal Desk.

SOURCE RULES
- Read only the Splash Sports ticket page open in my browser, including
  each ticket's expanded legs and detail view.
- Do not place, change or cancel picks. Do not change any account setting.
- Use no memory, no outside schedule, no other website and no guessed data.

HARD STOPS. Reply with one line starting "STOP:" and no JSON when:
- you cannot tell whether this is the Pending/Open or the
  Completed/History page (ask me);
- the page mixes pending and completed tickets (extract one type only);
- you cannot read the current date and time (ask me for it);
- tickets or legs are collapsed and you cannot expand them.

STEP 1. Page and identity.
- page_type: "pending" or "completed". date_code: "SPL-P-YYYYMMDD-HHMM"
  for pending, "SPL-C-YYYYMMDD-HHMM" for completed, from the Central date
  and minute of extraction.
- extracted_at_central: "YYYY-MM-DD HH:MM:SS CST" (or CDT) from the real
  clock. extracted_at_utc: the SAME instant as "YYYY-MM-DDTHH:MM:SSZ".
- coverage: what the page actually shows, e.g. "History, last 7 days,
  14 tickets".

STEP 2. Tickets. One object per ticket, every leg kept in order.
- ticket_type: exactly "single", "parlay" or "teaser". Anything else:
  keep it, use the closest type only if it is truly one of these, and add
  a warning naming the ticket.
- ticket_id: the real ticket ID if shown. Otherwise build a stable ID from
  observed ticket facts and the ordered selections, and describe the
  basis in ticket_id_basis. Never use the extraction time.
- ticket_time_as_shown: the ticket's own timestamp text exactly as shown,
  or null. ticket_time_label: the word the page prints next to it,
  exactly ("Placed", "Settled", "Locked", ...), or null if unlabeled.
- placed_at_central: only when the label says Placed, converted to
  "YYYY-MM-DD HH:MM:SS CST/CDT"; otherwise null.
- locked_at_central: only when the label says Locked; otherwise null.
- A ticket timestamp is NEVER a kickoff and NEVER a game date. Never copy
  it into any leg field.
- stake, potential_payout, payout, payout_multiplier: numbers as shown,
  or null. reported_result: the page's own result text, or null.

STEP 3. Legs.
- league: "NFL" or "NCAAF" from the source. If unclear: null plus a
  warning.
- away_team, home_team: labels exactly as shown. "A at B" or "A @ B"
  means away = A, home = B. home_away_certain true only with that
  notation or a home/away badge; otherwise false plus a warning.
- market: exactly "spread", "total" or "moneyline".
- selection: for totals exactly "Over" or "Under"; for spreads and
  moneylines the selected team copied exactly as away_team or home_team.
- line: the official number recorded on the ticket (not today's board
  line), as a number. PK = 0. Moneyline line is null.
- price: American odds as a number. This contest uses Even line odds, so
  spread and total legs show +100; write 100 when shown, else null.
  A MONEYLINE leg must have its real price: open the ticket detail to
  read it. If it is still not shown, set null AND add a warning naming
  the leg. Never default to -110 or +100.
- Teasers: teased_line is the final adjusted number the ticket displays;
  copy it to line as well. base_line only if the ticket shows it,
  otherwise null. Never add or subtract teaser points yourself. If the
  number's meaning is unclear: teased_line null plus a warning.
- selection_as_shown: the leg's original text.
- reported_result, final_score: as displayed, or null.

STEP 4. Leg kickoff and game date. All Central times use America/Chicago.
- kickoff_as_shown: the GAME's kickoff text exactly as shown on the leg
  or its detail view, including its zone, or null when no kickoff is
  shown. Ticket times do not count.
- kickoff_central: that kickoff converted to "YYYY-MM-DD HH:MM", 24-hour,
  with the date rolled over if needed, or null.
- kickoff_tz: ONLY "CST" or "CDT" (CST from early November to mid
  March, otherwise CDT), or null when kickoff_central is null. Never
  EST, ET, PST or UTC. The source zone stays inside kickoff_as_shown.
- game_date_central: the GAME's date "YYYY-MM-DD" when the leg or its
  detail view shows it, or when kickoff_central gives it; otherwise null.
- Day headers on a history page group tickets by placement or
  settlement. They are NOT game dates. Do not use them, and do not use
  placement, settlement, extraction time, ticket IDs, today's year or
  the contest title.
- Pending page: every leg needs kickoff_central; if missing, add a
  warning naming the leg.
- Completed page: every leg needs game_date_central or kickoff_central.
  If neither is shown even in the detail view, set both null and add a
  warning naming the leg. A known game date with no kickoff time is
  fine: put it in game_date_central, keep kickoff fields null, and add a
  note (not a warning).
- If a college game would be dated on a Sunday, or a game date falls
  before or after its ticket's placement in an impossible way, re-check
  the detail view; if it still conflicts, keep what is shown and add a
  warning.

STEP 5. notes and warnings. Both are JSON arrays of strings.
- notes: informational facts only.
- warnings: ONLY problems still unresolved after checking detail views.
  Any warning blocks import until I resolve it, so never hide a real
  problem in notes, and never invent one. Use [] when there is none.

OUTPUT FORMAT. Exactly these keys. Do not repeat source or date_code
inside tickets; the parent values apply.
{"schema":"signal-desk.splash-picks.v1","source":"Splash Sports Picks","date_code":"SPL-C-YYYYMMDD-HHMM","extracted_at_central":"YYYY-MM-DD HH:MM:SS CST","extracted_at_utc":"YYYY-MM-DDTHH:MM:SSZ","page_type":"completed","page_url":"... or null","page_title":"... or null","contest_name":"... or null","entry_name":"... or null","coverage":"...","ticket_count":0,"notes":[],"warnings":[],"tickets":[{"ticket_id":"...","ticket_id_basis":"... or null","ticket_type":"parlay","ticket_time_as_shown":"... or null","ticket_time_label":"... or null","placed_at_central":null,"locked_at_central":null,"stake":null,"potential_payout":null,"payout":null,"payout_multiplier":null,"reported_result":null,"legs":[{"league":"NFL","away_team":"...","home_team":"...","home_away_certain":true,"game_date_central":"YYYY-MM-DD","kickoff_central":null,"kickoff_tz":null,"kickoff_as_shown":null,"market":"spread","selection":"...","line":0,"price":100,"base_line":null,"teased_line":null,"reported_result":null,"final_score":null,"selection_as_shown":"..."}]}]}
- Numbers are JSON numbers, not strings. No "+" sign.
- Return the JSON object only, on ONE line: no Markdown fence, no
  commentary, no indentation, no trailing newline.
- Keep every ticket, leg and observed field. Never drop observations.

FINAL SELF-CHECK. Do every item silently, then output.
1. ticket_count equals the number of objects in tickets.
2. No leg's kickoff_as_shown equals its ticket's ticket_time_as_shown.
3. Every kickoff_tz is "CST", "CDT" or null.
4. Every moneyline leg has a numeric price, or a warning names it.
5. Every teaser leg has a numeric teased_line, or a warning names it.
6. Every completed leg has game_date_central or kickoff_central, or a
   warning names it. No game date came from a day header.
7. Each spread/moneyline selection equals that leg's away_team or
   home_team exactly; each total selection is Over or Under.
8. extracted_at_central and extracted_at_utc are the same instant and
   date_code matches page_type and the Central date and minute.
9. The output parses as one JSON object.

PRIVACY: the JSON contains contest and account details. Producing it does
not authorize publishing it.
```
