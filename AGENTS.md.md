\# AGENTS.md



\## Purpose



This repository contains a Telegram expense tracking bot with a growing analytics and recommendation system.



The primary development workflow for the recommendation module is defined in the dedicated skill:

`recommendation-module`.



\---



\## Core Rule



For any task related to recommendations, analytics, or financial insights:



➡️ ALWAYS use the `recommendation-module` skill as the source of truth.  

➡️ Follow its stages strictly and sequentially.  

➡️ Do NOT skip steps or reorder stages.  

➡️ Do NOT implement recommendation logic directly in handlers.



\---



\## Development Principles



\- Keep logic modular:

&#x20; - analytics → rules → ranking → formatting → handlers

\- Avoid mixing concerns (no SQL inside rules, no business logic in handlers).

\- Prefer deterministic and explainable logic over heuristics hidden in code.

\- Do not introduce LLM-based decision making for recommendations.



\---



\## Data Integrity Rules



\- Never break existing transaction, category, or project logic.

\- Preserve backward compatibility with existing bot behavior.

\- All new analytics must be based on existing data or clearly defined summary tables.

\- Treat large one-time purchases carefully (do not let them distort baselines).



\---



\## Recommendation System Constraints



\- Recommendations must be:

&#x20; - data-driven

&#x20; - explainable

&#x20; - numerically justified

\- Do not generate generic advice.

\- Do not show more than a small number of recommendations (top-N approach).

\- Avoid duplicate or redundant recommendations.



\---



\## When in Doubt



If implementation details are unclear:



1\. Check the `recommendation-module` skill.

2\. Prefer consistency with existing architecture.

3\. Choose the simplest solution that satisfies acceptance criteria.



\---



\## Out of Scope (for MVP)



\- No automatic push recommendations

\- No ML-based ranking

\- No complex personalization

\- No LLM-generated financial reasoning



\---



\## Summary



\- Use the skill for structure.

\- Keep implementation clean and modular.

\- Prioritize correctness, clarity, and maintainability.

