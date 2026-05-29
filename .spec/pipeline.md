# Pipeline SPEC

> Status: **Reviewed** — 修复 progress 架构、confidence 升级时机、category 枚举、digest overview
> Updated: 2026-05-26
> Scope: Collection, analysis, digest, and cleanup flow.

## 1. Main Daily Flow

```text
00:00 Beijing time (16:00 UTC)
  -> acquire run lock (skip if another run is running)
  -> create run record (status=running)
  -> fetch approved active sources (update stats_json after each source)
  -> normalize raw items
  -> deterministic deduplication (with cross-source tracking + confidence recompute)
  -> persist new items
  -> Stage 1 analysis (all new items, deepseek-v4-flash; update stats_json incrementally)
  -> compute expires_at from insight_score
  -> Stage 2 analysis (score >= 75, deepseek-v4-pro; update stats_json incrementally)
  -> generate digest per domain (call flash for overview)
  -> write digest as Hexo post to /opt/blog/source/_posts/
  -> backup digest markdown to OSS (via oss2 SDK)
  -> run cleanup (delete expired items)
  -> mark run succeeded/partial/failed
  -> release run lock
```

Worker 在每个步骤完成后增量更新 `runs.stats_json` 到 MySQL，API 从 `stats_json` 实时计算 progress。

If the run takes 8-9 hours, that is acceptable. Correctness and quality over speed.

## 2. Run Concurrency

**Only one run at a time.** Use MySQL advisory lock as the single lock source of truth.

Draft implementation:

- Acquire `GET_LOCK('intelligence_daily_pipeline', 0)` before creating or resuming a run.
- If lock cannot be acquired, skip the scheduled trigger.
- Release with `RELEASE_LOCK('intelligence_daily_pipeline')` in `finally`.
- If a stale `running` run is older than 12 hours, mark that run failed before starting a new one.
- Redis is not used for run locking in Phase 1.

The stale-run check is not the lock itself. It is only cleanup:

```python
existing = db.query(Run).filter(Run.status == 'running').first()
if existing:
    if existing.started_at < now() - timedelta(hours=12):
        # Stale run, force-fail it
        existing.status = 'failed'
        existing.error_json = {"reason": "stale_timeout"}
    else:
        # Still running, skip this scheduled trigger
        log.info(f"Skipping: run {existing.id} still running")
        return
```

12-hour stale timeout prevents permanent lock from crashes.

## 3. Run Window

- **Ingestion**: since last successful run's `window_end` (catches missed items).
- **Digest grouping**: by Beijing calendar date (user-facing semantics).

If no previous successful run exists, use 24 hours back.

## 4. Source Fetch Flow

For each active source:

```text
load source config
  -> execute collector by strategy (l1_rss / l1_api / l1_github)
  -> parse raw records
  -> emit RawItem[]
  -> record status in run stats_json
```

Failure policy:

| Condition | Health | Action |
|---|---|---|
| Success | `good` | Reset consecutive_failures to 0 |
| 1-2 consecutive failures | `degraded` | Log warning, continue |
| 3+ consecutive failures | `disabled` | Stop fetching, needs manual re-enable |

One source failure does not stop the run. All other sources continue.

## 5. Normalization

For each RawItem:

```text
validate required fields (title or content must exist)
  -> canonicalize URL (strip tracking params)
  -> normalize timestamp to UTC
  -> derive stable item ID
  -> compute dedup_hash
  -> create Item candidate
```

Reject if:
- No title and no content.
- Timestamp is > 7 days in the future (sanity check).

## 6. Deduplication

Priority:

1. Compute `dedup_hash` from canonical URL when URL exists.
2. Else compute `dedup_hash` from normalized title + content fingerprint.
3. Else compute `dedup_hash` from normalized title + source_id as last resort.
4. Derive stable `item.id` after dedup decision: `{source_id}:{native_id}` if available, else `{source_id}:{dedup_hash_prefix}`.

On duplicate found:
- Do not create new row.
- Append a source occurrence object to existing item's `also_seen_in` JSON.
- If existing item has `analysis_stage = 2`, recompute confidence via `derive_confidence()` and update `items.confidence` if changed. This is a field recomputation, not a re-analysis — Stage 2 is not re-triggered.
- If existing item has `analysis_stage < 2`, keep `confidence = null`; Stage 2 fields remain null until Stage 2 actually runs.
- Do not re-run analysis.

## 7. Stage 1 Analysis

Model: `deepseek-ai/deepseek-v4-flash` via NVIDIA.

Input: title, canonical_url, source name, authority, published_at, content_text.

Output JSON:

```json
{
  "category": "vulnerability",
  "tags": ["cve", "linux", "kernel"],
  "summary_zh": "...",
  "insight_score": 85,
  "credibility": "high"
}
```

### 7.1 Category 枚举

`category` 必须是以下值之一，或 `other`：

| Category | 语义 | 典型内容 |
|---|---|---|
| `vulnerability` | 漏洞披露 | CVE、GHSA、安全公告 |
| `exploit` | 武器化 / PoC | Exploit-DB、Metasploit 模块、PoC 代码 |
| `research` | 深度研究 | 论文、技术博客、长文分析 |
| `product` | 产品发布/更新 | 新模型发布、产品公告、版本更新 |
| `engineering` | 工程实践 | 架构复盘、生产经验、技术选型 |
| `tool` | 工具/开源项目 | 新工具发布、框架更新 |
| `incident` | 安全事件 | 数据泄露、攻击事件、威胁情报 |
| `discussion` | 社区讨论 | HN 讨论、Reddit 帖子、观点文章 |
| `other` | 以上不符 | 兜底 |

Rules:
- Output must parse as JSON.
- `insight_score` must be 0-100. Out of range → clamp.
- `category` must be in taxonomy above. Unknown value → set to `other`.
- On parse failure: one retry with repair prompt. Still failed → `stage1_error = 'model_parse_error'`, `analysis_stage = 0`.

`analysis_stage = 0` with `stage1_error IS NULL` means pending/not attempted. `analysis_stage = 0` with `stage1_error IS NOT NULL` means Stage 1 failed.

After Stage 1, compute `expires_at` from `insight_score`.

`stage1_prompt_version`: starts at `s1_v1`.

## 8. Stage 2 Analysis

Trigger: `insight_score >= 75`.

Model: `deepseek-ai/deepseek-v4-pro` via NVIDIA.

Input: item fields + Stage 1 results + source authority + also_seen_in context.

Output JSON:

```json
{
  "recommendation_reason": "...",
  "confidence": "tentative",
  "trend_signal": "emerging",
  "action_suggestion": "..."
}
```

`stage2_prompt_version`: starts at `s2_v1`.

### 8.1 Confidence 推导规则

Confidence 由 Stage 2 模型输出初始值，然后由代码按以下规则**校正**（模型输出不可信时以规则为准）：

| Confidence | 条件 |
|---|---|
| `tentative` | 默认值。单一来源，authority 非 `official` |
| `firm` | 满足以下任一：(a) source.authority = `official`；(b) `also_seen_in` 有 ≥1 个其他来源 |
| `confirmed` | 满足以下任一：(a) source.authority = `official` **且** `also_seen_in` 有 ≥1 个其他来源；(b) `also_seen_in` 有 ≥2 个其他来源 |

逻辑伪代码：

```python
def derive_confidence(item, source):
    is_official = source.authority == 'official'
    corroboration_count = len(item.also_seen_in or [])

    if is_official and corroboration_count >= 1:
        return 'confirmed'
    if corroboration_count >= 2:
        return 'confirmed'
    if is_official or corroboration_count >= 1:
        return 'firm'
    return 'tentative'
```

Confidence 在两个时机更新：
1. **Stage 2 完成时**：模型输出 → 代码校正 → 写入。
2. **Dedup 更新 `also_seen_in` 时**：仅当 item 已经 `analysis_stage = 2` 时重新调用 `derive_confidence()`，若结果变化则更新 `items.confidence`。不触发 Stage 2 重新分析。`analysis_stage < 2` 的 item 保持 Stage 2 字段为 null。

### 8.2 Trend Signal 赋值规则

`trend_signal` 由 Stage 2 模型在 prompt 中根据以下语义判断：

| Signal | 语义 | 典型场景 |
|---|---|---|
| `emerging` | 首次出现或刚被披露，影响面尚不明确但有扩散潜力 | 新 CVE 刚上 NVD、新产品发布、新论文 |
| `growing` | 已有多方关注，热度或影响正在上升 | PoC 公开后被多源转载、HN 登顶 |
| `stable` | 已知问题/持续讨论，无显著变化 | 常规安全补丁、稳定项目更新 |
| `declining` | 热度下降或已有成熟应对方案 | 旧漏洞已被广泛修补、讨论趋于冷淡 |

Trend signal 不做代码校正，完全依赖模型判断。若模型未输出或输出非法值，设为 `null`。

## 9. Digest Flow

```text
select items where:
  domain = target_domain
  AND analysis_stage >= 1
  AND insight_score >= 40 (candidate pool)
  AND fetched_at within digest date window
-> group by category
-> sort by insight_score DESC, confidence DESC
-> top N per category (configurable, default 5)
-> render Markdown template
-> call flash model for 2-3 sentence overview (always)
-> store digest row in MySQL
-> write Markdown as Hexo post (with frontmatter)
-> backup Markdown to OSS (via oss2 SDK)
-> update stats_json.digest.{domain}
```

When digest generation starts, set `stats_json.digest.status = "running"`. After each domain attempt, set `stats_json.digest.security` or `stats_json.digest.ai` to a digest result object:

```json
{
  "status": "succeeded",
  "digest_id": "2026-05-26:security",
  "hexo_path": "intelligence-security-2026-05-26.md",
  "oss_url": "https://...",
  "error": null
}
```

Use per-domain status values from data-model.md: `succeeded`, `failed`, `skipped`. After both domains are attempted, compute aggregate `stats_json.digest.status` using data-model.md §2.2 rules.

### 9.1 Digest Overview

每次生成 digest 都调用 `deepseek-v4-flash` 生成 2-3 句中文概述。

Input: 高价值 items 的 title + summary_zh + category 列表。
Output: 2-3 句话，概括当日情报要点和建议优先处理项。

Overview 生成失败时，使用模板兜底："今日共采集 {n} 条情报，高价值 {m} 条。"

### 9.2 Hexo Post 格式

文件名：`intelligence-{domain}-YYYY-MM-DD.md`
路径：`/opt/blog/source/_posts/intelligence-{domain}-YYYY-MM-DD.md`

Frontmatter:

```yaml
---
title: 安全情报日报 · 2026-05-26
date: 2026-05-26 08:06:00
tags:
  - intelligence
  - security
categories:
  - 情报日报
---
```

正文为 digest 的 Markdown 内容，包含：
- Overview（2-3 句总结）
- 按 category 分组的高价值 items（score ≥75，含 summary_zh、score、source、action_suggestion）
- Lower-value mentions 列表（score 40-74，仅标题和 score）
- 统计摘要（collected/analyzed/high_value/failed_sources）

### 9.3 OSS 备份

同一份 Markdown 内容通过 oss2 SDK 上传至 OSS：
- Bucket: `suuuuzsk`
- Key: `intelligence/digests/YYYY-MM-DD/{domain}.md`

Hexo 写入优先于 OSS 备份。OSS 上传失败不影响 run 状态（记 warning）。

## 10. Cleanup Flow

Daily, after digest generation:

```text
DELETE FROM items WHERE expires_at IS NOT NULL AND expires_at < NOW()
```

Must not run during active analysis. Run it as last step of the pipeline.

## 11. Error Categories

Stable categories for `stage1_error`, `stage2_error`, and `run.error_json`:

- `source_timeout`
- `source_http_error`
- `source_parse_error`
- `source_auth_error`
- `normalization_error`
- `duplicate`
- `model_timeout`
- `model_rate_limited`
- `model_parse_error`
- `model_provider_error`
- `oss_upload_error`
- `hexo_write_error`
- `db_error`
- `stale_timeout`

## 11.1 Final Run Status

Set `runs.status` at the end of the worker using data-model.md §2.2 run status rules:

- `succeeded`: useful output produced and no non-fatal failures recorded.
- `partial`: useful output produced, but one or more non-fatal failures recorded.
- `failed`: fatal error prevents useful output.

Always set `finished_at` when leaving `running`, including stale timeout and unhandled exception paths.

## 12. Run Progress 计算

运行期间需要报告 `progress`（0.0-1.0），计算方式：

```
progress = fetch_weight + stage1_weight + stage2_weight + digest_weight

fetch_weight   = (完成源数 / 总源数) × 0.3
stage1_weight  = (stage1.succeeded / stage1.total) × 0.4
stage2_weight  = (stage2.succeeded / stage2.total) × 0.2
digest_weight  = stats_json.digest.status in ("succeeded", "partial") ? 0.1 : 0.0
```

Progress 从 `runs.stats_json` 实时计算（API 查询时按公式派生），不单独存储。Worker 每完成一个步骤后增量更新 `stats_json` 到 MySQL，确保 API 能读到最新进度。

## 13. Open Questions

_None — all resolved._
