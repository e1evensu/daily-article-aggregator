# Intelligence System Design SPEC

> Status: **Reviewed** — simplified schema, scaffolding allowed, production gates pending
> Updated: 2026-05-26

## 1. Design Position

Conservative, inspectable Phase 1 system. No over-engineering.

```text
curated sources
  -> L1 collectors (RSS/API/GitHub)
  -> normalized items
  -> deduplication (with cross-source tracking)
  -> Stage 1 AI (flash, all items)
  -> retention scoring
  -> Stage 2 AI (pro, score >= 75)
  -> daily digest
  -> Hexo post + OSS backup + MySQL storage
  -> internal REST API
```

## 2. Architecture

```text
              internal consumers
      REST API / digest reader / blog
                     |
                service layer
                     |
             digest + query services
                     |
              analysis pipeline
   dedup -> stage1 -> threshold -> stage2
                     |
              normalized items
                     |
           collection dispatcher
    RSS / API / GitHub collectors (L1 only)
                     |
              curated sources

Storage:
  MySQL on 114       items, sources, runs, digests (via SSH tunnel)
  Redis on 114       lightweight cache only (via SSH tunnel); not required for Phase 1 run locking
  Hexo posts         primary digest publication path
  OSS                digest markdown backup
```

## 3. Schema Summary

4 tables in Phase 1:

| Table | Purpose |
|---|---|
| `sources` | Source config + health + domain |
| `runs` | Pipeline execution log + per-source stats (JSON) |
| `items` | Normalized items + inline analysis fields |
| `digests` | Daily digest artifacts |

Plus `site_experiences` (mostly empty until Phase 2 L2/L3).

No `channels` table (domain is an enum field).
No `item_analysis` table (merged into items).
No `source_fetches` table (merged into runs.stats_json).

See `.spec/data-model.md`.

## 4. Key Design Decisions

| Decision | Choice | Why |
|---|---|---|
| No channels table | domain enum on sources/items | Avoids pointless JOINs for 2 fixed values |
| Analysis inline in items | No separate item_analysis | 99% reads want both, avoid JOIN tax |
| Per-source stats in runs JSON | No source_fetches table | 10 sources, JSON is enough |
| Run concurrency lock | MySQL advisory lock + stale run check | Single source of truth with runs table; avoids split-brain Redis/MySQL locking |
| Cross-source dedup | `also_seen_in` JSON field | Supports confidence upgrades |
| Prompt versioning | `s1_v1` / `s2_v1` labels | Simple, in code |
| Docker network_mode: host | Containers use host SSH tunnels | Simplest path to MySQL/Redis |
| Hard delete expired items | No tombstones | Keep run-level stats instead |

## 5. Technology Choices

| Area | Choice |
|---|---|
| Language | Python 3.12+ |
| API | FastAPI |
| ORM | SQLAlchemy 2 async |
| Scheduler | APScheduler in worker process |
| Cache | Redis on 114 (optional lightweight cache; NOT queue, NOT run lock source of truth) |
| DB | MySQL 8 on 114 (Docker) |
| Object storage | Aliyun OSS (via oss2 SDK) |
| AI | NVIDIA NIM (deepseek-v4-flash/pro) |
| Package manager | uv |
| Container | Docker Compose (network_mode: host) |

## 6. Design Constraints

- Phase 1 scope: 10 sources, 2 domains, no dashboard, no social scraping.
- Do not build for hypothetical scale — build for 200-500 items/day.
- Do not rely on unlimited provider assumptions.
- Treat reference projects as inspiration, not spec.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Source quality is poor | Curated catalog, trial status, auto-disable |
| NVIDIA rate limits hit | Conservative concurrency, fallback to Sub2API |
| MySQL fulltext weak for Chinese | Validate ngram, fallback to LIKE |
| SSH tunnel drops | autossh + systemd auto-restart |
| Run takes too long | Acceptable (8-9h), stale timeout at 12h |
