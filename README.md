# Audience request translator

A CRM manager describes an audience in plain words. The tool answers the way a good analyst would:
it builds the audience (logic, count and query) when the request is clear, asks when it's ambiguous,
and pushes back when it can't or shouldn't be done.

This is Option B of the case. My note on Parts 1 to 3 and how I used AI is in [`NOTE.md`](NOTE.md).

## Run it

**In Claude Code** (recommended)
1. Open this folder in Claude Code.
2. Type `/audience` followed by a request, for example:
   `/audience App users in Portugal who opened the app in the last 30 days but don't have an upcoming booking. Push only.`
3. If it asks questions, answer with one letter per question (for example "a, b") and it builds the audience.
   Built audiences are also saved as a CSV (the list) and a SQL file (the query, for Analytics) in `output/`.

**Without AI** (Python 3.9+, nothing to install)
- `python3 -m audience --examples` runs the six manager requests using Claude's readings of them, saved in `examples/`, so no AI is needed. Answers are printed and saved to `output/`, with a CSV of each built audience.
- `python3 -m unittest discover tests` runs the checks.

## How it works

```
manager's request
    │
    ▼
Claude reads it            picks from a fixed menu
    │
    ▼
structured request         market, channel, filters, flags
    │
    ▼
fixed code decides         build, ask or push back, then applies the policy
    │
    ▼
answer for the manager
```

| Step | Who does it | Why |
|---|---|---|
| Understanding the request, spotting undefined words | Claude | Language is where AI adds value |
| Deciding build, ask or push back | Code | The outcome must follow the rules, not a judgment call |
| Consent, complaints, bounced emails, one person per email | Code, on every query | These must always hold; Claude can't switch them off |
| Data clean-up (market spellings, duplicates, latest consent) | Code | Same answer every time |
| Building the query and counting | Code, from tested building blocks | Claude never writes SQL |
| Counts, table and rule explanations | Code | Same layout and wording every time |
| Wording of questions and notes | Claude, checked by code | Field names removed; key questions always asked |

## The six requests

| # | Request | Answer |
|---|---|---|
| 1 | Spain, email consent, completed booking in the last 12 months | ✅ 302 people |
| 2 | High-value customers in Germany, no booking in 9 months | ❓ What is "high-value"? Leave out people with a booking ahead? Which channel? |
| 3 | Portugal app users, opened the app in 30 days, no upcoming booking, push | ✅ 91 people |
| 4 | Everybody who cancelled in October | ❓ Which October? Cancelled during or for October? Leave out people who already booked again? Which channel? |
| 5 | Customers likely to churn | ⛔ No churn model in the data; offers a simple rule instead |
| 6 | Dormant list, regardless of consent, "service message" | ⛔ Only Legal classifies service messages; consent can't be skipped |

Full answers: [`examples/answers/`](examples/answers/), or run the examples. Dates in the answers count from 6 Nov 2026, the date the data catalogue sets as today for the case.

## How I checked it works
- **Recount:** the two audiences the tool builds (Spain email and Portugal push) are rebuilt a second way, in plain Python over the raw tables without the tool's SQL. The counts match.
- **Verdicts:** each of the six requests gets the expected kind of answer.
- **Tricky rules on a hand-made database:** every market spelling counts, duplicates count once, the latest consent across a person's records wins, two records updated at the same moment that disagree count as no, email consent doesn't count for push, bounced emails only block email, open complaints block every channel.
- **Saved query:** the self-contained query saved for Analytics gives the same count as the tool.
- **Follow-ups:** answered the questions for the high-value Germany and cancelled-in-October requests, and checked that the tool then builds the audience.
- **New requests:** ran it live in Claude Code on requests it hadn't seen, and fixed what came up.
- **Same words, same list:** ran the high-value Germany request in separate sessions with the same answers. Both gave 70.

`python3 -m unittest discover tests` runs 27 checks in about a second.

## What testing changed
The most useful find: in a live test, Claude read "haven't booked in 9 months" as "no rental taken" (78 people) instead of "no new booking made" (70). Same words, a different list, and the answer didn't say which meaning it had used, so a manager couldn't have noticed. Two changes came out of it. Common phrases now have fixed meanings, so the same words always give the same list. And every time-based filter now states its meaning under "Please check", so a different reading is always visible to the manager.

Other changes from testing:
- **Questions it can act on, every time.** Claude only offers options the tool can build, and key questions (like leaving out people who already booked again) are checked in code, so they're never skipped.
- **Answers a manager can use.** A zero result shows what other channels would reach, the list and the query are saved as files, and an answer only explains the rules the request touched.
- **Market and language are separate.** The first version could only filter by where people live, so a test request for "German speakers" could only be built as "lives in Germany". In this data that's a different list: 213 people in Germany prefer English. I added a preferred-language filter, and when a request names a language, the tool checks with the manager which list they mean.
- **Fast enough to use.** A request with no market took minutes, because the data clean-up (market spellings, duplicates, latest consent) covered every customer and was redone for each rule the tool checked. Now it runs once at the start of each request and every check reuses it. Answers take under a second, and a test checks they give the same count as the query saved for Analytics.

## Data issues found
I found nine problems and gaps in the data, and each one changes who ends up in an audience. For example, Germany is written four ways (DE, de, Germany, DEU), so a filter on "DE" alone would miss about one in five people living there. Duplicate customers can also disagree on their email consent. The tool handles each issue in code. The full list, with how big each issue is, how it's handled and my questions for the catalogue owner: [`docs/data_catalogue_gaps.md`](docs/data_catalogue_gaps.md).

## What I'd do next
- Test it on real requests. I learned the most from requests worded in ways the tool hadn't seen before, like "haven't booked", which turned out to mean two different lists. So the next test set is the managers' own last requests, compared with what Analytics delivered.
- Keep turning every issue found into a permanent check, as I did while building, so a fixed problem can't come back. For example, in one live test Claude skipped the question about leaving out people who had already booked again. Now the code always asks it, and a test fails if it doesn't.
- Track how often managers correct a reading. That rate decides when it moves from suggesting audiences to building them on its own.
- If the corrections show the wording Claude writes (questions, notes) still slips, add a second AI step that reviews the answer against the rules before the manager sees it. Anything that can be checked in code stays in code.
- Log every request, answer and approval, as an audit trail and to see where it gets corrected.
- Agree shared definitions with the team (high-value, lapsed, active) and add them to the menu.
- Push approved audiences to SFMC once there's API access.
- Add contact history, so it can respect contact pressure.
