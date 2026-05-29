# Requirements SPEC

> Status: **Reviewed**
> Updated: 2026-05-26

## 1. Product Goal

Personal intelligence system: collect, analyze, store, publish high-signal intelligence.

First useful product = stable daily intelligence flow:

```text
trusted sources -> collection -> dedup -> AI analysis -> storage -> daily digest -> Hexo post + OSS backup
```

Phase 1: security + AI domains only.

## 2. Consumers

| Consumer | Need | Phase |
|---|---|---|
| Owner | Daily security/AI brief | Phase 1 |
| Blog | Markdown digest written as Hexo post; OSS backup | Phase 1 |
| Internal agents | REST API queries | Phase 1 |
| Feishu | Push digest + alerts | Phase 2 |
| Finance agent | Market signal feed | Phase 3 |

## 3. Phase 1 Requirements

### R1. Source Ingestion

Small curated set. Phase 1 types: RSS, public API, GitHub API, internal API (SecHub/aihot).

Not Phase 1: WeChat, X/Twitter, CDP browser, generic crawling.

### R2. Deduplication

Deterministic: canonical URL hash > normalized title + content fingerprint > normalized title + source_id fallback. Source-native ID is used for stable `item.id`, not for cross-source duplicate detection.

Cross-source: same content from multiple sources tracked via `also_seen_in`.

### R3. AI Analysis

Two-stage pipeline:

- Stage 1 (all items): category, tags, summary_zh, insight_score, credibility. Model: deepseek-v4-flash via NVIDIA.
- Stage 2 (score >= 75): recommendation_reason, confidence, trend_signal, action_suggestion. Model: deepseek-v4-pro via NVIDIA.

Output must be valid JSON. Invalid = retry once, then mark failed.

### R4. Daily Digest

Generated when run finishes (not fixed time). Separate security and AI digests. Stored in MySQL, written as Hexo posts, and backed up to OSS.

### R5. Storage

MySQL on 114 for structured data and run locking. Redis on 114 is optional lightweight cache only; Phase 1 has no task queue. Hexo post output is the primary blog path; OSS stores backup digest artifacts.

### R6. Internal API

Localhost only. Items, digests, sources, runs, stats.

### R7. Data Retention

| Score | Retention |
|---|---|
| < 10 | Immediate delete |
| 10-29 | 5 days |
| 30-49 | 10 days |
| 50-74 | 30 days |
| >= 75 | Permanent |

Hard delete. Run-level stats preserved.

## 4. Non-Functional

- One bad source must not fail the whole run.
- AI failure captured per item.
- Re-running is idempotent.
- Only one run at a time (concurrency lock).
- Model/provider recorded per analysis.
- No secrets in git.
- API not public.

## 5. Out of Scope (Phase 1)

Dashboard, Feishu push, X/Twitter, browser automation, entity graph, finance, MCP, vector search, multi-user.
