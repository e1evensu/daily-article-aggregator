# Tasks SPEC

> Status: **Phase 1a–1e + frontend prototype sync code-complete (uncommitted) — systemd API/scheduler running; Hexo + limited manual dry-run + repeatable release smoke passed; commit-style manual run/stability gates still open**
> Updated: 2026-05-31

## 1. Current Status / 当前状态

Phase 1a–1e 的实现代码已基本写完，前端原型已同步至 Phase 1 数据契约，`make verify` 通过；Hexo 真实写入探针、限量 manual dry-run smoke、Docker compose 构建/镜像导入 smoke 和临时端口 release API runtime smoke 已通过，并已固化为 `make verify-release`。但**整套实现仍有大量未提交的工作区改动**，且**提交型 manual pipeline run、48h 稳定性和 compose 正式切换仍未过 gate**。当前仍有旧 unified 系统（见 §1.1 快照）并行存在；本仓库是按 `.spec/` 重写、用于替换它的新系统。

已落地（代码存在且可编译，详见 §3 勾选）：
- 脚手架 / 配置 / SQLAlchemy 模型 + 异步引擎 + 初始迁移
- 采集器（RSS / GitHub / NVD / 内部 API）+ dispatcher + 归一去重 + 源健康跟踪
- 两段式 AI（flash / pro）+ 重试退避 + 保留期 `expires_at` + 错误处理
- 输出（digest 生成 + Hexo 写入 + OSS 备份）+ REST API（items / digests / sources / runs / stats，游标分页）
- 编排（APScheduler cron + run lock + run 生命周期 + cleanup + 源目录加载）
- 前端原型同步（`styles.css`、canonical source IDs、stage-specific analysis fields、source occurrence `also_seen_in`、source status、digest `hexo_path` / `oss_url`）
- 运维 gate 脚本（migration/source seed/source feed verification/AI gate/release smoke）纳入 lint + compileall；非 Phase 1 扩源脚本仅生成 deferred inactive proposals

仍未完成 / 被 gate 阻塞：
- §2 剩余生产门槛（提交型 manual run / 48h stability）尚未验证
- 当前实际运行方式仍是 systemd + worktree，尚未切换到 compose 正式运行

### 1.1 Implementation Snapshot / 实现快照 (2026-05-31)

| 维度 | 状态 |
|---|---|
| 代码 | Phase 1a–1e 模块齐全（`src/{config,db,models,collector,ai,pipeline,api,scheduler}`），前端原型已同步 Phase 1 contract，`make verify` 通过 |
| Git | 已有 feature 分支提交，但当前仍有大量未提交/未跟踪改动；生产服务直接从工作区运行 |
| 测试 | 本地 `make verify` 通过：ruff、pytest 115 项、compileall |
| 运行态 | `intelligence-api.service`(:8100) 和 `intelligence-scheduler.service` 已由 systemd 运行；API smoke passed for `/health`, `/sources`, `/stats`, `/items`, `/digests`；`run_pipeline.py --dry-run --max-items 2` passed with per-domain limiting, rollback + temp Hexo output；`make verify-release` passed compose config/build, image help/import, and release image API runtime smoke on temporary `127.0.0.1:18100` |
| 线上现状 | 新 GEN2 API/scheduler 已在本机运行；旧系统 `/opt/unified-intelligence-system`（`osint_orchestrator`, :8900, 公网看板 `/intel/` + 飞书 + OSS）仍并行存在；MySQL / Redis 在 114，经 `intelligence-tunnel.service` (autossh) 接入 |
| 数据（旧系统库） | 30 条 item（全部 stage1 已分析，stage2=0，高价值=0），10 源 health=good |

> 注意：本仓库（`/home/suuuu/develop/intelligence-system`, :8100, `src.main:app`, `/api/v1/*`）与旧 unified 系统（:8900, `osint_orchestrator`, sub2api 网关, 公网 `/api/intel/*`）端口、API 前缀、AI 网关、是否对外都不同，不是同一套代码。新系统目标是按 spec 重写并最终替换旧系统。

## 2. Remaining Gates

- [x] Test NVIDIA rate limit behavior — production concurrency 3 passed (3/3 in 84.5s); non-gating 10-concurrency stress completed 10/10 in 164.8s
- [x] Test JSON output on sample items (Stage 1 prompt) — `ai_gate_test.py` now passes Stage-1 JSON samples with hard-timeout retry and production concurrency 3
- [x] Verify at least 3 source feed/API URLs are reachable from 38 — external-network run passed 7/8 parseable public sources after HN concurrent item fetch; `ai_arxiv` currently fetches 0 parseable entries because the arXiv RSS channel is empty for the checked window
- [x] Promote at least 3 sources from `candidate` to `approved` — canonical catalog and DB now have 7 approved public sources; internal sources and `ai_arxiv` remain candidate
- [x] Confirm Hexo direct-write path and permissions on the blog host — `write_hexo_post` wrote/read/removed a temporary probe in `/opt/blog/source/_posts/`
- [x] Limited manual pipeline dry-run smoke — `run_pipeline.py --dry-run --max-items 2` passed with 7 approved sources, per-domain limiting, Stage 1 4/4, Stage 2 1/1, security + AI digests succeeded, DB rolled back, Hexo output in temp dir, OSS disabled
- [x] Docker compose release build/import smoke — `make verify-release` runs `docker-compose config --quiet`, `docker-compose build`, image `run_pipeline.py --help`, and env-backed image import of `src.main` / `src.scheduler.jobs`; passed
- [x] Release image API runtime smoke — `make verify-release` started a temporary container on `127.0.0.1:18100`, passed `/health` and DB-backed `/api/v1/sources/security_nvd_cve`, then removed it; systemd `:8100` stayed active
- [ ] Commit-style manual pipeline run: run once under systemd/workdir settings, commit DB changes, verify new items + digest
- [ ] 48h stability run

These can run in parallel with scaffolding, but must pass before scheduled production runs.

## 3. Implementation Backlog

> 勾选依据：2026-05-31 在 `/home/suuuu/develop/intelligence-system` 核对源码 + `make verify` 通过。勾选表示“代码已实现且本地质量门通过”，**不代表已上线 / 已过生产 gate**（见 §1.1、§2）。

### Phase 1a — Scaffolding ✅

- [x] Python project: pyproject.toml + uv + Dockerfile + docker-compose.yml
- [x] Config: pydantic-settings from .env — `src/config.py`
- [x] Database: SQLAlchemy models + async engine + initial migration SQL — `src/models/*`, `src/db.py`, `migrations/001_init.sql`
- [x] Makefile: dev, test, migrate, run, docker, release-smoke targets — `Makefile`

### Phase 1b — Collection ✅

- [x] Collector base class (RawItem output contract) — `src/collector/base.py`
- [x] RSS collector (feedparser) — `src/collector/rss.py`
- [x] GitHub API collector (GHSA advisories) — `src/collector/github.py`
- [x] API collector interface (for SecHub/aihot) — `src/collector/api.py`
- [x] Collection dispatcher (iterate sources, record per-source status) — `src/collector/dispatcher.py`
- [x] Normalization + dedup — `src/pipeline/ingestion.py`
- [x] Source health tracking (consecutive failures → disable) — `dispatcher.py` + `models/source.py`
- [x] (额外) NVD collector — `src/collector/nvd.py`

### Phase 1c — Analysis ✅

- [x] AI client (OpenAI-compatible, NVIDIA provider, no arbitrary max_token cap) — `src/ai/client.py`
- [x] Stage 1 prompt + parser (category/tags/summary/score/credibility) — `src/ai/prompts.py`, `analyzer.py`
- [x] Stage 2 prompt + parser (recommendation/confidence/trend/action) — `src/ai/prompts.py`, `analyzer.py`
- [x] Retention: compute expires_at from insight_score — `analyzer.py` / `models/item.py` / `pipeline/cleanup.py`
- [x] Analysis error handling (retry + backoff, then record error) — `analyzer.py` (`retry_backoff_s` per stage)

### Phase 1d — Output ✅

- [x] Digest generator (group by category, render Markdown) — `src/pipeline/digest.py` (`build_digest_artifact`)
- [x] Hexo post writer (frontmatter + `/opt/blog/source/_posts/`) — `src/pipeline/output.py` (`write_hexo_post`)
- [x] OSS backup upload (oss2 SDK) — `src/pipeline/output.py`
- [x] REST API: items, digests, sources, runs, stats — `src/api/*`, mounted under `/api/v1` in `src/main.py`
- [x] Cursor pagination — `src/api/items.py`, `src/api/contracts.py`

### Phase 1d-front — Frontend Prototype Sync ✅

- [x] Add or restore `src/front/styles.css` — `index.html` 引用文件已存在
- [x] Replace fixture source IDs with canonical long IDs from `.spec/source-catalog.md`
- [x] Replace fixture/display analysis fields with `stage1_*` and `stage2_*`
- [x] Change `also_seen_in` fixture/display shape to source occurrence objects
- [x] Display source `status` separately from health; do not label candidates as approved
- [x] Display digest `hexo_path` and `oss_url` from API response
- [x] Keep CDN/Babel runtime as prototype-only; production dashboard remains out of Phase 1 scope

### Phase 1e — Orchestration ✅

- [x] APScheduler daily job — `src/scheduler/jobs.py`（cron 由 `settings.collect_cron` 驱动，按 UTC；确认值为 `0 16 * * *` 即北京 00:00）
- [x] Run concurrency lock (only one run at a time) — `src/pipeline/run_lifecycle.py`
- [x] Run lifecycle: create → fetch → analyze → digest → cleanup → complete — `src/pipeline/run_lifecycle.py`, `runner.py`
- [x] Cleanup job: delete expired items — `src/pipeline/cleanup.py`
- [x] Source config loader/sync (loads canonical catalog; dispatcher fetches only `approved`; runtime API list/detail/stats queries filter to Phase 1 catalog/domains) — `src/collector/catalog.py`

### Phase 1f — Deploy / Runtime ⏳

- [x] API + scheduler on 38 via systemd — `intelligence-api.service` and `intelligence-scheduler.service` running from this worktree
- [x] Docker compose build/import smoke — `make verify-release` covers compose config, image build, CLI help, and module import with `.env`; passed
- [x] Release image API runtime smoke — `make verify-release` started a temporary host-network container on `127.0.0.1:18100`, served health + DB-backed source detail, and removed it
- [ ] Docker compose runtime cutover — current actual runtime is still systemd + worktree
- [x] Limited smoke test: `run_pipeline.py --dry-run --max-items 2` verified collect → Stage 1 → Stage 2 → security + AI digests → Hexo temp write → rollback
- [ ] Commit-style smoke test: manual run, verify persisted items + digest
- [ ] 48h stability run

## 4. Phase 2 Backlog (Not Now)

- [ ] Feishu webhook push  — 旧 unified 系统已有飞书 gateway 代码（webhook 未配）；新系统 Phase 2 再做
- [ ] X/Twitter crawling research
- [ ] L2 collectors (Jina Reader)
- [ ] Entity extraction
- [ ] MCP Server
- [ ] Trend detection
- [ ] More sources

## 5. Next Steps / 下一步建议

1. **提交工作区** — 把 Phase 1a–1e 实现先 commit（当前 57 个文件未提交，有丢失风险），按规范走 `feature/*` → PR。
2. **补齐剩余生产门槛**（§2）— 提交型 manual run、48h stability。
3. **收敛部署方式**（§3 Phase 1f）— `make verify-release` 已证明 release image 可构建、导入并临时服务 API；仍需决定是否从 systemd worktree 切到 compose runtime，再考虑与旧 `:8900` unified 系统的切换/下线。
