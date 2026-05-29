# API SPEC

> Status: **Reviewed** — 修复 digest 字段映射、合并搜索端点、统一命名
> Updated: 2026-05-26

## 1. API Boundary

Internal only in Phase 1. Bind to `127.0.0.1:8100`.

Lightweight token auth even for localhost (configurable via `API_TOKEN` env var, can be disabled for dev).

Canonical source IDs come from `.spec/source-catalog.md` and use the long form, e.g. `security_nvd_cve`. Do not introduce legacy short aliases such as `sec_nvd`, `sec_ghsa`, or `ai_hn` in API responses, item IDs, run stats, fixtures, or migrations.

## 2. Resources

### 2.1 Items

```text
GET /api/v1/items
GET /api/v1/items/{item_id}
```

Query parameters for `GET /api/v1/items`:

| Param | Type | Notes |
|---|---|---|
| `domain` | string | `security`, `ai`, `all` |
| `category` | string | Category filter (see pipeline.md §7.1) |
| `min_score` | int | Minimum insight_score |
| `analysis_stage` | int | `0`, `1`, `2` — filter by analysis depth |
| `confidence` | string | `tentative`, `firm`, `confirmed` |
| `trend_signal` | string | `emerging`, `growing`, `stable`, `declining` |
| `source_id` | string | Filter by source |
| `q` | string | Full-text search (MySQL FULLTEXT on title + summary_zh + content_text) |
| `since` | ISO timestamp | Published after |
| `until` | ISO timestamp | Published before |
| `cursor` | string | Opaque cursor for pagination |
| `limit` | int | Default 20, max 100 |

Default sort: `insight_score DESC`. When `q` is present, sort by relevance first, then `insight_score DESC`.

Item response fields (shown as the value of `data` in the JSON envelope):

```json
{
  "id": "security_nvd_cve:CVE-2026-31415",
  "source_id": "security_nvd_cve",
  "domain": "security",
  "title": "...",
  "canonical_url": "https://...",
  "author": "NVD",
  "published_at": "2026-05-26T05:14:00Z",
  "fetched_at": "2026-05-26T07:36:00Z",
  "also_seen_in": [
    {"source_id": "security_github_advisories", "url": "...", "seen_at": "..."}
  ],
  "category": "vulnerability",
  "tags": ["cve", "linux", "kernel"],
  "summary_zh": "...",
  "insight_score": 92,
  "credibility": "high",
  "confidence": "confirmed",
  "trend_signal": "emerging",
  "recommendation_reason": "...",
  "action_suggestion": "...",
  "analysis_stage": 2,
  "stage1_model": "deepseek-ai/deepseek-v4-flash",
  "stage1_provider": "nvidia",
  "stage1_prompt_version": "s1_v1",
  "stage1_analyzed_at": "2026-05-26T07:39:00Z",
  "stage2_model": "deepseek-ai/deepseek-v4-pro",
  "stage2_provider": "nvidia",
  "stage2_prompt_version": "s2_v1",
  "stage2_analyzed_at": "2026-05-26T07:43:00Z",
  "expires_at": null
}
```

Stage 2 fields (`confidence`, `trend_signal`, `recommendation_reason`, `action_suggestion`) are `null` when `analysis_stage < 2`.

### 2.2 Digests

```text
GET /api/v1/digests
GET /api/v1/digests/latest
GET /api/v1/digests/{date}?domain=security
```

| Param | Type | Notes |
|---|---|---|
| `domain` | string | `security`, `ai`, `all` |
| `format` | string | `json`, `markdown` |

Digest JSON response (shown as the value of `data` in the JSON envelope):

```json
{
  "id": "2026-05-26:security",
  "date": "2026-05-26",
  "domain": "security",
  "title": "安全情报日报 · 2026-05-26",
  "summary": "...",
  "stats_json": {"collected": 35, "analyzed": 35, "high_value": 4, "failed_sources": 1},
  "highlights_json": [{
    "name": "vulnerability",
    "label": "漏洞披露",
    "count": 2,
    "item_ids": ["security_nvd_cve:CVE-2026-31415", "security_github_advisories:GHSA-7q4f-pgqx-h3vh"]
  }],
  "generated_at": "2026-05-26T08:06:00Z",
  "hexo_path": "intelligence-security-2026-05-26.md",
  "oss_url": "https://suuuuzsk.oss-cn-guangzhou.aliyuncs.com/intelligence/digests/2026-05-26/security.md"
}
```

Response `data` 字段与 DB 列名一致（`summary`、`stats_json`、`highlights_json`）。

`hexo_path` 从 `date + domain` 派生（`intelligence-{domain}-YYYY-MM-DD.md`），不存 DB，computed at query time。

`highlights_json[].item_ids` 引用 items 的 ID，前端可据此展开详情。

`format=markdown` 时不使用 JSON envelope，直接返回 `content_markdown` 字段内容，Content-Type 为 `text/markdown`。

### 2.3 Sources

```text
GET /api/v1/sources
GET /api/v1/sources/{source_id}
```

No mutation endpoints in Phase 1.

Source response fields (shown as the value of `data` in the JSON envelope):

```json
{
  "id": "security_nvd_cve",
  "name": "NVD CVE Feed",
  "domain": "security",
  "type": "api",
  "url": "https://services.nvd.nist.gov/rest/json/cves/2.0",
  "authority": "official",
  "status": "approved",
  "health": "good",
  "consecutive_failures": 0,
  "is_active": true,
  "last_fetch_at": "2026-05-26T07:36:00Z",
  "last_fetch_status": "succeeded",
  "today_items": 18,
  "spark": [12, 8, 14, 11, 22, 17, 9, 13, 18, 21, 14, 18]
}
```

Computed fields (not stored in `sources` table, derived at query time):

| Field | Computation |
|---|---|
| `today_items` | `COUNT(items) WHERE source_id = ? AND fetched_at >= today_start_beijing` |
| `spark` | 14-element array, each = item count for that day (newest last). `SELECT DATE(fetched_at) as d, COUNT(*) FROM items WHERE source_id = ? AND fetched_at >= now() - 14 days GROUP BY d` |

### 2.4 Runs

```text
GET /api/v1/runs
GET /api/v1/runs/{run_id}
GET /api/v1/runs/latest
```

Run response fields (shown as the value of `data` in the JSON envelope):

```json
{
  "id": "run_20260526_000000",
  "kind": "daily",
  "status": "running",
  "window_start": "2026-05-25T07:50:00Z",
  "window_end": "2026-05-26T07:50:00Z",
  "started_at": "2026-05-26T07:36:00Z",
  "finished_at": null,
  "progress": 0.78,
  "stats_json": {
    "sources": {
      "security_nvd_cve": {"status": "succeeded", "items": 18, "duration_s": 3.2},
      "security_portswigger": {"status": "failed", "error": "source_timeout", "duration_s": 30.0}
    },
    "stage1": {"total": 63, "succeeded": 61, "failed": 2},
    "stage2": {"total": 9, "running": 3, "succeeded": 6, "failed": 0},
    "dedup_skipped": 8,
    "retention_deleted": 0,
    "digest": {
      "status": "running",
      "security": null,
      "ai": null
    }
  }
}
```

`progress` 从 `stats_json` 实时计算（见 pipeline.md §12），不存 DB：

```
完成源数 / 总源数 × 0.3           (FETCH 权重 30%)
+ stage1.succeeded / stage1.total × 0.4  (STAGE 1 权重 40%)
+ stage2.succeeded / stage2.total × 0.2  (STAGE 2 权重 20%)
+ (stats_json.digest.status in ("succeeded", "partial") ? 0.1 : 0) (DIGEST 权重 10%)
```

Note: API 返回的 `stats_json` 字段就是 DB 中的 `runs.stats_json` 列（JSON 直出，无 rename）。

See data-model.md §2.2 for the `stats_json.digest` schema and valid status values.

### 2.5 Stats

```text
GET /api/v1/stats
GET /api/v1/stats?date=2026-05-26
```

Stats is a **read-only aggregation endpoint**. All data derived from items/runs/sources.

Response (shown as the value of `data` in the JSON envelope):

```json
{
  "date": "2026-05-26",
  "items": {
    "total": 63,
    "by_domain": {"security": 35, "ai": 28},
    "high_value": 6,
    "failed_analyses": 2,
    "delta_vs_yesterday": 12
  },
  "sources": {
    "total": 10,
    "healthy": 9,
    "degraded": 1,
    "disabled": 0
  },
  "score_histogram": {
    "buckets": [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95],
    "counts": [2, 1, 3, 2, 4, 1, 3, 2, 5, 3, 4, 2, 3, 1, 2, 3, 2, 1, 1, 0]
  },
  "confidence_breakdown": {
    "tentative": 2,
    "firm": 3,
    "confirmed": 1
  },
  "retention_buckets": {
    "permanent": 6,
    "30_days": 8,
    "10_days": 12,
    "5_days": 15,
    "delete": 3
  },
  "category_counts": {
    "vulnerability": 12,
    "exploit": 5,
    "research": 8,
    "product": 6,
    "engineering": 4,
    "tool": 3,
    "incident": 2,
    "discussion": 3
  }
}
```

## 3. Response Shape

All JSON endpoints use an envelope. Resource examples above show the object inside `data`.

Single-resource success:

```json
{
  "data": {},
  "meta": {"request_id": "...", "next_cursor": null}
}
```

List response:

```json
{
  "data": [],
  "meta": {"request_id": "...", "next_cursor": "eyJpZCI6...", "total": 63}
}
```

Error:

```json
{
  "error": {"code": "not_found", "message": "Item not found"},
  "meta": {"request_id": "..."}
}
```

## 4. Pagination

Cursor-based for item lists. Cursor is opaque (base64 encoded `insight_score` + `id` for score-sorted lists, or `published_at` + `id` for time-sorted).

Default page size: 20. Max: 100.

## 5. Deferred Endpoints

Phase 2+:

```text
POST /api/v1/analyze         (on-demand analysis)
POST /api/v1/runs/trigger    (manual trigger via API)
GET  /api/v1/entities        (entity graph)
GET  /api/v1/trends          (trend detection)
POST /api/v1/sources         (add source via API)
PATCH /api/v1/sources/{id}   (update source)
```
