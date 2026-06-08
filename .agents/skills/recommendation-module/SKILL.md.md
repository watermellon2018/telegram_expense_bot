\# Skill: Recommendation Module (MVP)



\## Purpose



Implement a deterministic, explainable recommendation system for a Telegram expense tracking bot.



The system must:

\- analyze user financial data,

\- detect meaningful signals,

\- generate recommendations using rules,

\- rank and filter them,

\- return a small set of high-quality insights.



This skill defines a \*\*strict step-by-step execution plan\*\*.



\---



\## Global Rules



\- Follow stages strictly in order.

\- Do NOT skip stages.

\- Do NOT start the next stage until the current one is complete.

\- After each stage:

&#x20; 1. Summarize what was done

&#x20; 2. List modified/created files

&#x20; 3. Confirm acceptance criteria

\- Use deterministic logic only (no LLM reasoning for recommendations).

\- Keep architecture modular:

&#x20; analytics → rules → ranking → formatting → handler



\---



\# =========================

\# STAGE 1 — Database Layer

\# =========================



\## Goal

Create storage for recommendation system and analytics summaries.



\## Tasks





\### 4. Create monthly\_user\_summary table

Must include BOTH:

\- full metrics

\- baseline-adjusted metrics



Core fields:

\- total\_expense\_full

\- total\_income\_full

\- net\_balance\_full

\- tx\_count

\- avg\_check

\- median\_check

\- recurring\_amount\_full

\- recurring\_share\_full

\- small\_expense\_amount\_full

\- small\_expense\_share\_full

\- total\_expense\_baseline\_adjusted

\- recurring\_amount\_baseline\_adjusted



\---



\### 5. Create monthly\_category\_summary table

Fields:

\- user\_id

\- month\_key

\- category\_id

\- total\_amount\_full

\- total\_amount\_baseline\_adjusted

\- tx\_count

\- share\_in\_month



\---



\## Acceptance Criteria



\- All tables created via migrations

\- Models/repositories implemented

\- No impact on existing functionality



\---



\# =========================

\# STAGE 2 — Outlier Handling

\# =========================



\## Goal

Prevent large one-time purchases from breaking analytics.



\## Tasks



\### 1. Extend transaction model

Add:

\- is\_large\_one\_time\_purchase

\- outlier\_score

\- outlier\_flag\_source



\---



\### 2. Implement outlier detection service



Use multi-signal logic:

\- ratio to user median

\- ratio to category median

\- rarity in history

\- non-recurring behavior

\- distribution tail detection



DO NOT use only "3 sigma".



\---



\### 3. Implement baseline-adjusted metrics



\- full metrics = everything

\- adjusted metrics = exclude or down-weight flagged transactions



\---



\### 4. Implement robust baseline



Use:

\- median

\- trimmed mean



NOT raw average only.



\---



\## Acceptance Criteria



\- Large one-time purchases are detected

\- Adjusted metrics differ from full metrics correctly

\- Baseline is stable under extreme values



\---



\# =========================

\# STAGE 3 — Analytics Layer

\# =========================



\## Goal

Build analytics snapshot used by recommendation engine.



\## Tasks



\### Build analytics snapshot including:



\#### A. Current state

\- total expense

\- total income

\- net balance

\- tx count

\- avg \& median check

\- top category

\- most frequent category

\- most expensive purchase

\- most expensive day



\---



\#### B. Dynamics

\- vs previous month

\- vs 3-month baseline

\- vs same day previous month

\- spend pace

\- forecast



\---



\#### C. Structure

\- category shares

\- small expense share

\- recurring share

\- project vs personal spend



\---



\#### D. Behavioral

\- weekday vs weekend

\- post-income spikes

\- repeated small transactions



\---



\#### E. Positive signals

\- category reduction

\- improved balance

\- reduced recurring share



\---



\## Acceptance Criteria



\- Single analytics snapshot object exists

\- No SQL inside rules

\- Snapshot fully deterministic



\---



\# =========================

\# STAGE 4 — Rule Engine

\# =========================



\## Goal

Generate candidate recommendations.



\## Implement Rules:



\### Core

\- forecast\_overspend

\- total\_growth\_vs\_prev\_month

\- total\_growth\_vs\_3m\_baseline



\### Category

\- category\_growth\_vs\_prev\_month

\- category\_growth\_vs\_3m\_baseline



\### Recurring

\- high\_recurring\_share

\- recurring\_review



\### Behavioral

\- small\_expenses\_accumulation

\- weekday\_spending\_pattern



\### Financial optimization

\- cashback\_opportunity



\### Positive

\- positive\_category\_reduction



\---



\## Rule Requirements



Each rule must:

\- use analytics snapshot only

\- check:

&#x20; - minimum history

&#x20; - absolute thresholds

&#x20; - outlier distortion

\- return structured candidate



\---



\## Acceptance Criteria



\- Rules produce candidates

\- No noise from small values

\- Outliers do not break logic



\---



\# =========================

\# STAGE 5 — Ranking \& Selection

\# =========================



\## Goal

Select best recommendations.



\## Implement scoring:



score = base\_priority + severity + impact + confidence - penalty



\### Components:

\- base\_priority (by type)

\- severity (% change)

\- impact (absolute money)

\- confidence (data quality)

\- novelty penalty (from history)



\---



\### Implement:

\- scoring service

\- confidence calculation

\- novelty penalty (history-based)

\- deduplication:

&#x20; - max 1 per category

&#x20; - remove similar signals

\- top-N selection (default = 3)



\---



\## Acceptance Criteria



\- Ranking prioritizes meaningful signals

\- No duplicates

\- Max 3 recommendations returned



\---



\# =========================

\# STAGE 6 — Formatting

\# =========================



\## Goal

Convert recommendations to user text.



\## Requirements



\- clear and short

\- include numbers

\- neutral tone

\- avoid blaming



\---



\### Special Case: Outliers



If comparison is distorted:

\- explain limitation



Example:

"Previous month included a large one-time purchase"



\---



\## Acceptance Criteria



\- All recommendation types formatted

\- Output readable and useful



\---



\# =========================

\# STAGE 7 — Bot Integration

\# =========================



\## Goal

Expose recommendations via Telegram bot.



\## Tasks



\- create handler/command

\- call full pipeline:

&#x20; analytics → rules → ranking → formatting

\- save recommendation history

\- send response



\---



\## Acceptance Criteria



\- User can request recommendations

\- Response returns correctly

\- History is saved



\---



\# =========================

\# STAGE 8 — Feedback

\# =========================



\## Goal

Collect user feedback.



\## Tasks



\- add actions:

&#x20; - like

&#x20; - dislike

&#x20; - dismiss

\- store events



\---



\## Acceptance Criteria



\- Feedback stored

\- System ready for future personalization



\---



\# =========================

\# STAGE 9 — Testing

\# =========================



\## Goal

Ensure system correctness.



\## Tests required:



\- analytics correctness

\- outlier detection

\- rule triggering

\- ranking behavior

\- deduplication

\- end-to-end flow



\---



\## Acceptance Criteria



\- Core logic covered by tests

\- No regressions



\---



\# FINAL NOTE



This system must remain:



\- deterministic

\- explainable

\- modular

\- resistant to outliers



Do NOT:

\- use ML ranking

\- use LLM reasoning

\- generate generic advice



Focus on correctness over complexity.

