# Review Checklist

> Status: **Updated** — core SPEC aligned; production gate still open
> Updated: 2026-05-31

## 1. Resolved Contradictions

| Item | Was | Now |
|---|---|---|
| Push channel | Telegram vs Feishu vs OSS | **Hexo post (Phase 1), Feishu (Phase 2)** |
| Digest time | 08:00 UTC fixed | **Run finished = push, no fixed time** |
| Stage 2 threshold | >= 60 vs >= 75 | **>= 75** |
| Redis location | 38 vs 114 vs none | **114 (Docker, installed)** |
| Entity graph | Phase 1 vs Phase 2 | **Phase 2** |
| API exposure | Public vs internal | **Internal only** |
| channels table | Separate table vs enum | **Enum field on sources/items, no table** |
| item_analysis | Separate table vs inline | **Inline in items table** |
| NVIDIA model IDs | "needs verification" | **Available: deepseek-v4-flash, deepseek-v4-pro** |
| DB name/user | TBD | **intelligence / intelligence** |
| Blog digest path | OSS-only vs Hexo direct write | **Hexo direct write (主路径), OSS backup** |
| Confidence 推导 | Undefined | **代码校正：tentative/firm/confirmed 基于 authority + also_seen_in** |
| Trend signal | Undefined | **模型判断：emerging/growing/stable/declining** |
| API source fields | Basic only | **补充 spark(14天)/today_items 聚合字段** |
| Run progress | In-memory vs API | **从 stats_json 实时计算，worker 增量写 MySQL** |
| stats_json.digest | 结构未定义 | **定义 aggregate status、per-domain result、更新时机** |
| Run final status | partial/succeeded/failed 边界不清 | **定义 run status 判定表** |
| analysis_stage=0 | pending 与 Stage 1 failed 混用 | **用 stage1_error 区分 pending vs failed** |
| Stats endpoint | Vague | **明确返回 histogram/category/confidence/retention 聚合** |
| Hexo frontmatter | Undefined | **title/date/tags/categories 格式确认** |
| Digest 字段名 | API 和 DB 不一致 (overview/categories) | **统一为 DB 列名：summary、highlights_json、stats_json** |
| Category 枚举 | 未定义 | **9 个值：vulnerability/exploit/research/product/engineering/tool/incident/discussion/other** |
| Digest overview | "optionally" call model | **Always call flash model，失败用模板兜底** |
| 搜索端点 | /items 和 /items/search 边界不清 | **合并为 /items?q=keyword，删除独立 search 端点** |
| Redis 角色 | "task queue + dedup cache" 但实际无 queue | **optional cache only；MySQL advisory lock 是 run lock 唯一来源** |
| OSS 上传方式 | rclone vs SDK 不确定 | **oss2 SDK（Python worker 直接上传）** |
| 内部源网络 | 10.0.0.114 内网 IP 不可达 | **需加 SSH 隧道 18210/18220，source URL 改为 localhost** |
| data-model open questions | D1/D2 未关闭 | **已关闭，答案写入 Resolution 列** |

## 2. Open Items

| Item | Status | Owner |
|---|---|---|
| Stage 1 JSON long-tail latency | Closed by `ai_gate_test.py` hard-timeout retry; latest gate passed sample JSON + concurrency 3 | Implementation |
| HN keyword filter list | Needs definition | Implementation |
| Sub2API fallback | Not tested | Phase 1 or deferred |
| Approved source set | 7 public sources approved and synced; internal sources + arXiv remain candidate | Implementation |
| arXiv source quality | Current RSS check returned 0 parseable entries because the channel was empty | Implementation |
| SecHub/aihot 服务部署 | 服务未上线，tunnel 未配置 | 基础设施 |

## 3. Implementation Gate

Scaffolding gate is open:

- [x] Phase 1 scope agreed (security + AI, no dashboard/social/finance)
- [x] Source catalog has canonical Phase 1 sources (7 approved public + 3 candidate)
- [x] Model IDs available on NVIDIA
- [x] Infra deployed (MySQL, Redis, tunnels, .env)
- [x] Schema reviewed and simplified
- [x] Main contradictions resolved
- [x] API response shapes documented, field names match DB
- [x] Confidence/trend rules formalized with execution timing
- [x] Hexo integration path confirmed
- [x] Category enum defined (9 values)
- [x] Progress architecture defined (stats_json → computed)
- [x] Redis role clarified (optional cache only, not queue/lock)
- [x] OSS upload method confirmed (oss2 SDK)
- [x] All spec open questions closed

Production-run gate is still closed:

- [x] At least 3 sources approved and reachable from 38 — `verify_feeds.py --min-ok 3 --timeout-s 10` passed 7/8 public sources after HN concurrent fetch fix
- [x] Stage 1 JSON output tested on sample items — `ai_gate_test.py` passed sample JSON checks with hard-timeout retry
- [x] NVIDIA rate-limit behavior tested — Stage 1 production concurrency 3 passed; 10-concurrency stress completed but was slow
- [x] Hexo direct-write path verified — `write_hexo_post` wrote/read/removed a temporary probe in `/opt/blog/source/_posts/`
- [x] Limited manual dry-run smoke — `run_pipeline.py --dry-run --max-items 2` passed collect → Stage 1 4/4 → Stage 2 1/1 → security + AI digests with DB rollback, temp Hexo output, OSS disabled
- [x] Docker compose release build/import smoke — `make verify-release` runs `docker-compose config --quiet`, `docker-compose build`, image `run_pipeline.py --help`, and env-backed image import of `src.main` / `src.scheduler.jobs`; passed
- [x] Release image API runtime smoke — `make verify-release` started a temporary host-network container on `127.0.0.1:18100`, passed `/health` and DB-backed `/api/v1/sources/security_nvd_cve`, then removed it
- [ ] Commit-style manual run verified persisted items + digest
- [ ] 48h stability run
- [ ] Docker compose runtime cutover
- [ ] SecHub/aihot tunnel configured (if these sources are needed for first run)

Production gate tooling is ready:

- [x] `verify_feeds.py` uses real collectors, prints per-source status, and hard-times out each source subprocess
- [x] `ai_gate_test.py` exits non-zero if Stage 1 JSON or production concurrency checks fail
- [x] `run_pipeline.py --dry-run --max-items N` provides a bounded per-domain manual smoke path that rolls back DB changes, writes Hexo output to a temp dir, and disables OSS upload
- [x] `make verify-release` verifies the Docker release path: excludes `.env` from build context, builds an image, preserves `--loop asyncio`, exposes CLI help without requiring production env, imports runtime modules with `.env`, serves API traffic from the image on a temporary port, and cleans up the container
- [x] Non-Phase-1 source proposals are deferred and inactive by default, not auto-approved
- [x] API list/detail/stats queries are constrained to Phase 1 domains and canonical catalog source IDs, so legacy DB rows do not leak through current endpoints

Frontend gate is closed:

- [x] `src/front/styles.css` exists and page renders without missing assets
- [x] Fixture source IDs match `.spec/source-catalog.md`
- [x] Fixture item fields match `.spec/data-model.md` and `.spec/api.md`
- [x] Sources view displays source `status` separately from health
- [x] Digest view uses `summary` / `highlights_json` field names

Backend scaffolding can proceed against the SPECs. Scheduled production runs should wait for the production-run gate.
