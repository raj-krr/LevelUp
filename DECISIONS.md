# DECISIONS.md — LevelUp

This file logs any ambiguity in the spec and the decision taken.

| # | Decision | Reasoning | Date |
|---|----------|-----------|------|
| 1 | System fonts only (no Google Fonts) | Zero network cost, instant load, excellent Indic script support on Android | 2026-10-31 |
| 2 | Inline CSS + JS in index.html | Single network request to load the entire UI — critical for low-bandwidth users | 2026-10-31 |
| 3 | Dark mode via CSS `prefers-color-scheme` only (no manual toggle) | Keeps UI simple; respects user's OS setting | 2026-10-31 |
| 4 | Rate limit store is per-process in-memory dict | Simple, no Redis needed; resets on restart — acceptable for hackathon scope | 2026-10-31 |

