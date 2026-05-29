# Data Model SPEC

> Status: **Reviewed** — 关闭所有 open questions，补充 category 枚举引用
> Updated: 2026-05-26
> Scope: Phase 1 schema.

## 1. Design Goals

- Source configuration and health.
- Idempotent ingestion runs with concurrency lock.
- Normalized intelligence items with inline analysis fields.
- Deterministic deduplication with cross-source tracking.
- Score-based retention via \`expires_at\`.
- Internal search.

Entity graph, profiles, trends are Phase 2+.

## 2. Tables

### 2.1 \`sources\`

| Field | Type | Notes |
|---|---|---|
| \`id\` | varchar(64) PK | Stable source ID, e.g. \`security_nvd_cve\` |
| \`name\` | varchar(200) | Display name |
| \`domain\` | enum('security','ai','finance','general') | Direct domain, no FK |
| \`type\` | enum('rss','api','github_api','internal_api') | Phase 1 types only |
| \`url\` | varchar(1000) | Feed/API URL |
| \`auth_mode\` | varchar(50) | \`none\`, \`api_key\`, \`bearer\`, \`internal\` |
| \`fetch_strategy\` | varchar(50) | \`l1_rss\`, \`l1_api\`, \`l1_github\` |
| \`authority\` | enum('official','authoritative','regular') | |
| \`status\` | enum('candidate','trial','approved','rejected','deferred') | Default \`candidate\`; dispatcher fetches only \`approved\` |
| \`health\` | enum('good','degraded','disabled') | Default \`good\` |
| \`consecutive_failures\` | int | Default 0 |
| \`last_fetch_at\` | timestamp nullable | UTC |
| \`last_fetch_status\` | varchar(50) | |
| \`config_json\` | json | Source-specific parser config |
| \`is_active\` | boolean | Default true |
| \`created_at\` | timestamp | UTC |
| \`updated_at\` | timestamp | UTC |

No \`channels\` table — \`domain\` is a direct enum on sources and items.

### 2.2 \`runs\`

One scheduled or manual pipeline execution.

| Field | Type | Notes |
|---|---|---|
| \`id\` | varchar(64) PK | Run ID, e.g. \`run_20260526_160000\` |
| \`kind\` | varchar(50) | \`daily\`, \`manual\`, \`backfill\` |
| \`status\` | enum('running','partial','succeeded','failed') | See run status rules below |
| \`window_start\` | timestamp | UTC |
| \`window_end\` | timestamp | UTC |
| \`started_at\` | timestamp | UTC |
| \`finished_at\` | timestamp nullable | UTC |
| \`stats_json\` | json | Counts by stage + per-source fetch status |
| \`error_json\` | json nullable | Error summary |

\`stats_json\` includes per-source fetch results and coarse pipeline step state (replaces \`source_fetches\` table):

\`\`\`json
{
  "sources": {
    "security_nvd_cve": {"status": "succeeded", "items": 12, "duration_s": 3.2},
    "security_portswigger": {"status": "failed", "error": "timeout", "duration_s": 30.0}
  },
  "stage1": {"total": 45, "succeeded": 43, "failed": 2},
  "stage2": {"total": 8, "succeeded": 8, "failed": 0},
  "dedup_skipped": 5,
  "retention_deleted": 3,
  "digest": {
    "status": "pending",
    "security": null,
    "ai": null
  }
}
\`\`\`

`stats_json.digest` contract:

| Field | Type | Values / Shape | Updated when |
|---|---|---|---|
| `status` | string | `pending`, `running`, `succeeded`, `partial`, `failed` | `pending` when run starts; `running` when digest generation begins; final value after both domain digests attempt |
| `security` | object nullable | `null` before attempt, else digest result object below | After security digest attempt |
| `ai` | object nullable | `null` before attempt, else digest result object below | After AI digest attempt |

Digest result object:

```json
{
  "status": "succeeded",
  "digest_id": "2026-05-26:security",
  "hexo_path": "intelligence-security-2026-05-26.md",
  "oss_url": "https://...",
  "error": null
}
```

Per-domain digest result `status` values: `succeeded`, `failed`, `skipped`. Use `skipped` only when no eligible items exist for that domain; it is not an error.

Aggregate `stats_json.digest.status`:
- `pending`: digest step has not started.
- `running`: digest step is in progress.
- `succeeded`: both domain results are `succeeded` or `skipped`, and at least one domain is `succeeded`.
- `partial`: at least one domain is `succeeded` and at least one domain is `failed`.
- `failed`: all attempted domain results are `failed`, or digest generation crashes before a domain result is recorded.

**Concurrency lock**: The worker must acquire MySQL advisory lock `GET_LOCK('intelligence_daily_pipeline', 0)` before creating or resuming a run, and release it in `finally` via `RELEASE_LOCK`. Redis is not the lock source of truth. After acquiring the lock, check `runs.status='running'`: if the run is older than 12 hours, mark it failed with `stale_timeout`; otherwise skip the trigger.

Run status rules:

| Final status | Condition |
|---|---|
| `running` | Run has started and final status is not decided yet |
| `succeeded` | No fatal pipeline error; at least one source succeeded; Stage 1 finished for all persisted new items; digest aggregate status is `succeeded`; cleanup completed |
| `partial` | Pipeline completed enough to preserve useful output, but one or more non-fatal failures occurred: some sources failed, some item analyses failed, Stage 2 failed for some eligible items, OSS upload failed, or digest aggregate status is `partial` |
| `failed` | Fatal error prevents useful output: cannot acquire required DB/resources after lock, no approved source could be fetched, Stage 1 cannot run for any persisted item due to provider/system failure, Hexo write fails for all generated digests, digest aggregate status is `failed`, stale timeout, or unhandled exception |

One source failure alone must not make the run `failed`; it makes the run `partial` if the rest of the pipeline produces useful output.

### 2.3 \`items\`

Normalized items with **inline analysis fields** (no separate item_analysis table).

| Field | Type | Notes |
|---|---|---|
| \`id\` | varchar(96) PK | Stable item ID |
| \`source_id\` | varchar(64) FK | Canonical long ID from `.spec/source-catalog.md`; no short aliases |
| \`domain\` | enum('security','ai','finance','general') | Denormalized from source |
| \`run_id\` | varchar(64) FK nullable | First seen run |
| \`title\` | varchar(500) | |
| \`canonical_url\` | varchar(1000) | |
| \`content_text\` | mediumtext nullable | Extracted text/markdown |
| \`author\` | varchar(200) nullable | |
| \`published_at\` | timestamp nullable | UTC |
| \`fetched_at\` | timestamp | UTC |
| \`dedup_hash\` | varchar(64) | Unique |
| \`also_seen_in\` | json nullable | Cross-source occurrences, e.g. \`[{"source_id":"security_exploitdb","url":"...","seen_at":"..."}]\` |
| \`metadata_json\` | json nullable | Source-specific fields |
| — Stage 1 — | | |
| \`category\` | varchar(50) nullable | See pipeline.md §7.1 for enum values |
| \`tags\` | json nullable | |
| \`summary_zh\` | varchar(500) nullable | |
| \`insight_score\` | tinyint unsigned nullable | 0-100 |
| \`credibility\` | enum('high','medium','low','unknown') | Default \`unknown\` |
| — Stage 2 (filled only when score >= 75) — | | |
| \`confidence\` | enum('tentative','firm','confirmed') nullable | Filled only when `analysis_stage = 2` |
| \`recommendation_reason\` | text nullable | |
| \`trend_signal\` | enum('emerging','growing','stable','declining') nullable | |
| \`action_suggestion\` | text nullable | |
| — Analysis metadata — | | |
| \`analysis_stage\` | tinyint | 0=Stage 1 not successfully completed, 1=Stage 1 done, 2=Stage 2 done |
| \`stage1_model\` | varchar(200) nullable | Exact model used for Stage 1 |
| \`stage1_provider\` | varchar(100) nullable | \`nvidia\`, \`sub2api\` |
| \`stage1_prompt_version\` | varchar(50) nullable | e.g. \`s1_v1\` |
| \`stage1_analyzed_at\` | timestamp nullable | |
| \`stage1_error\` | varchar(200) nullable | Error type if Stage 1 failed |
| \`stage2_model\` | varchar(200) nullable | Exact model used for Stage 2 |
| \`stage2_provider\` | varchar(100) nullable | \`nvidia\`, \`sub2api\` |
| \`stage2_prompt_version\` | varchar(50) nullable | e.g. \`s2_v1\` |
| \`stage2_analyzed_at\` | timestamp nullable | |
| \`stage2_error\` | varchar(200) nullable | Error type if Stage 2 failed |
| — Retention — | | |
| \`expires_at\` | timestamp nullable | null = permanent |
| \`created_at\` | timestamp | UTC |

Indexes:

- UNIQUE on \`dedup_hash\`
- \`(domain, insight_score DESC)\`
- \`(domain, published_at DESC)\`
- \`(source_id)\`
- \`(expires_at)\` — for cleanup job
- FULLTEXT on \`(title, summary_zh, content_text)\` WITH PARSER ngram

`analysis_stage = 0` is disambiguated by `stage1_error`:
- `analysis_stage = 0` and `stage1_error IS NULL`: pending/not attempted yet.
- `analysis_stage = 0` and `stage1_error IS NOT NULL`: Stage 1 attempted and failed.
- Stage 2 failure does not reset `analysis_stage` to 1; keep `analysis_stage = 1`, set `stage2_error`, and keep Stage 2 fields null.

Why inline instead of separate \`item_analysis\`:
- 99% of reads want item + analysis together — no JOIN tax
- Phase 1 will not re-analyze items
- If re-analysis needed later, add a \`item_analysis_history\` append table
- Stage-specific metadata is still separate as `stage1_*` and `stage2_*`, so Stage 2 does not overwrite Stage 1 audit data.

### 2.4 \`digests\`

| Field | Type | Notes |
|---|---|---|
| \`id\` | varchar(96) PK | e.g. \`2026-05-26:security\` |
| \`run_id\` | varchar(64) FK nullable | |
| \`date\` | date | Beijing date |
| \`domain\` | varchar(32) | \`security\`, \`ai\`, \`all\` |
| \`title\` | varchar(200) | |
| \`summary\` | text nullable | |
| \`stats_json\` | json | |
| \`highlights_json\` | json | Item IDs and display metadata |
| \`content_markdown\` | mediumtext | |
| \`oss_url\` | varchar(1000) nullable | |
| — Computed (not stored) — | | |
| \`hexo_path\` | _(derived)_ | \`intelligence-{domain}-YYYY-MM-DD.md\`, computed from \`date\` + \`domain\` |
| \`generated_at\` | timestamp | UTC |

UNIQUE on \`(date, domain)\`.

### 2.5 \`site_experiences\`

| Field | Type | Notes |
|---|---|---|
| \`domain_name\` | varchar(200) PK | e.g. \`portswigger.net\` |
| \`best_strategy\` | varchar(50) | |
| \`rate_limit\` | int nullable | |
| \`notes\` | text nullable | |
| \`last_success\` | timestamp nullable | |
| \`failure_count\` | int | Default 0 |

Phase 1 mostly unused, but schema ready for Phase 2 L2/L3.

## 3. Removed Tables

| Table | Reason |
|---|---|
| \`channels\` | Just an enum. \`domain\` field on sources/items replaces it. |
| \`item_analysis\` | Merged into \`items\`. No JOIN tax on every read. |
| \`source_fetches\` | Per-source fetch status lives in \`runs.stats_json\`. |
| \`retention_class\` | Derivable from \`insight_score\`. \`expires_at\` is enough. |

## 4. Retention Rules

Computed from \`insight_score\` at Stage 1 completion:

| Score | \`expires_at\` |
|---|---|
| < 10 | Immediate (do not persist, or set to \`now()\`) |
| 10-29 | \`stage1_analyzed_at + 5 days\` |
| 30-49 | \`stage1_analyzed_at + 10 days\` |
| 50-74 | \`stage1_analyzed_at + 30 days\` |
| >= 75 | \`null\` (permanent) |

Hard delete expired items. Run-level aggregate stats preserved in \`runs.stats_json\`.

## 5. Deduplication

Priority order:

1. `dedup_hash`: Prefer canonical URL hash when URL exists. This is the primary cross-source identity.
2. `dedup_hash`: Else normalized title + content fingerprint.
3. `dedup_hash`: Else normalized title + source_id hash as last resort.
4. `item.id`: Stable row ID. Use `{source_id}:{native_id}` when a source-native ID exists; otherwise use `{source_id}:{dedup_hash_prefix}`. Do not use `item.id` to decide cross-source duplicates.

Cross-source handling: If \`dedup_hash\` already exists from a different source, do not create new row. Instead append a source occurrence object to existing item's \`also_seen_in\` JSON array. This supports confidence upgrades without losing where the duplicate was seen.

## 6. Prompt Versioning

Prompt versions use semantic labels:

- \`s1_v1\` — Stage 1 initial prompt
- \`s1_v2\` — Stage 1 after tuning categories
- \`s2_v1\` — Stage 2 initial prompt

Prompts live in code (\`src/ai/prompts.py\`). Bump version when prompt changes materially. Old items keep their original stage-specific version tag — no backfill unless explicitly requested.

## 7. Search

Phase 1: MySQL FULLTEXT with ngram parser.

Items endpoint supports `q` parameter for full-text search (see api.md §2.1).

Validate Chinese search quality on real data before committing. Fallback: `LIKE` search for internal use.

## 8. Open Questions

_None — all resolved._

| ID | Question | Resolution |
|---|---|---|
| ~~D1~~ | Should `dedup_hash` be unique globally or per-domain? | **Global.** `also_seen_in` tracks cross-source occurrences |
| ~~D2~~ | Store raw AI response for debugging? | **Only on failure.** `stage1_error`/`stage2_error` store categories; raw response goes to debug logs, not DB |
