# Tasks SPEC

> Status: **Phase 1a–1e implementation code-complete (uncommitted) — frontend sync, deploy, and validation gates still open**
> Updated: 2026-05-29

## 1. Current Status / 当前状态

Phase 1a–1e 的实现代码已基本写完，`python -m compileall src` 通过；但**整套实现仍是未提交的工作区改动**，且 **测试未运行、系统未部署**。当前线上跑的是旧的 unified 系统（见 §1.1 快照），本仓库是按 `.spec/` 重写、用于替换它的新系统。

已落地（代码存在且可编译，详见 §3 勾选）：
- 脚手架 / 配置 / SQLAlchemy 模型 + 异步引擎 + 初始迁移
- 采集器（RSS / GitHub / NVD / 内部 API）+ dispatcher + 归一去重 + 源健康跟踪
- 两段式 AI（flash / pro）+ 重试退避 + 保留期 `expires_at` + 错误处理
- 输出（digest 生成 + Hexo 写入 + OSS 备份）+ REST API（items / digests / sources / runs / stats，游标分页）
- 编排（APScheduler cron + run lock + run 生命周期 + cleanup + 源目录加载）

仍未完成 / 被 gate 阻塞：
- 前端原型同步（§3 Phase 1d-front，2026-05-29 复核仍全部未做）
- 部署（§3 Phase 1f：`:8100` 未监听，未 `docker compose up`）
- §2 所有生产门槛（NVIDIA 限流 / JSON 输出 / 源可达 / candidate→approved / Hexo 权限）均未验证

### 1.1 Implementation Snapshot / 实现快照 (2026-05-29)

| 维度 | 状态 |
|---|---|
| 代码 | Phase 1a–1e 模块齐全（`src/{config,db,models,collector,ai,pipeline,api,scheduler}`），`compileall src` 通过 |
| Git | 仅 2 commit（`Initial spec scaffold` + `Document CodeGraph indexing`）；**约 57 个文件未提交**，整套实现都在工作区 |
| 测试 | 15 个测试文件已写（`tests/test_*.py`），但 venv 未装 pytest 等 dev 依赖，**尚未运行**，pass/fail 未知 |
| 部署 | **未部署**：`intelligence-api`(:8100) 未监听，worker 未起 |
| 线上现状 | 旧系统 `/opt/unified-intelligence-system`（`osint_orchestrator`, :8900, 公网看板 `/intel/` + 飞书 + OSS）仍在运行；MySQL / Redis 在 114，经 `intelligence-tunnel.service` (autossh) 接入 |
| 数据（旧系统库） | 30 条 item（全部 stage1 已分析，stage2=0，高价值=0），10 源 health=good |

> 注意：本仓库（`/home/suuuu/develop/intelligence-system`, :8100, `src.main:app`, `/api/v1/*`）与旧 unified 系统（:8900, `osint_orchestrator`, sub2api 网关, 公网 `/api/intel/*`）端口、API 前缀、AI 网关、是否对外都不同，不是同一套代码。新系统目标是按 spec 重写并最终替换旧系统。

## 2. Remaining Gates

> 全部未验证（2026-05-29）。代码已就绪，可逐项跑验证。

- [ ] Test NVIDIA rate limit behavior (send 10 rapid requests)
- [ ] Test JSON output on 3-5 sample items (Stage 1 prompt)
- [ ] Verify at least 3 source feed/API URLs are reachable from 38
- [ ] Promote at least 3 sources from `candidate` to `approved`  — catalog 默认 `status="candidate"`，尚未提升
- [ ] Confirm Hexo direct-write path and permissions on the blog host  — `write_hexo_post` 已实现，权限/目录存在性未实测

These can run in parallel with scaffolding, but must pass before scheduled production runs.

## 3. Implementation Backlog

> 勾选依据：2026-05-29 在 `/home/suuuu/develop/intelligence-system` 核对源码 + `compileall` 通过。勾选表示“代码已实现”，**不代表已跑测试 / 已上线**（见 §1.1、§2）。

### Phase 1a — Scaffolding ✅

- [x] Python project: pyproject.toml + uv + Dockerfile + docker-compose.yml
- [x] Config: pydantic-settings from .env — `src/config.py`
- [x] Database: SQLAlchemy models + async engine + initial migration SQL — `src/models/*`, `src/db.py`, `migrations/001_init.sql`
- [x] Makefile: dev, test, migrate, run, docker targets — `Makefile`

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

### Phase 1d-front — Frontend Prototype Sync ⛔ (复核 2026-05-29：全部未做)

- [ ] Add or restore `src/front/styles.css` — `index.html` 引用了 `styles.css`，但文件缺失，入口页无法按设计渲染
- [ ] Replace fixture source IDs with canonical long IDs from `.spec/source-catalog.md` — 仍是 `sec_nvd`/`ai_hn` 等短 ID，未改为 `security_nvd_cve`
- [ ] Replace fixture/display analysis fields with `stage1_*` and `stage2_*` — `data.js` 中无 `stage1_/stage2_` 字段
- [ ] Change `also_seen_in` fixture/display shape to source occurrence objects — 仍是字符串数组 `['sec_ghsa', ...]`
- [ ] Display source `status` separately from health; do not label candidates as approved
- [ ] Display digest `hexo_path` and `oss_url` from API response — 前端未引用
- [ ] Decide whether CDN/Babel runtime is prototype-only or replace it with bundled/vendor static assets

### Phase 1e — Orchestration ✅

- [x] APScheduler daily job — `src/scheduler/jobs.py`（cron 由 `settings.collect_cron` 驱动，按 UTC；确认值为 `0 16 * * *` 即北京 00:00）
- [x] Run concurrency lock (only one run at a time) — `src/pipeline/run_lifecycle.py`
- [x] Run lifecycle: create → fetch → analyze → digest → cleanup → complete — `src/pipeline/run_lifecycle.py`, `runner.py`
- [x] Cleanup job: delete expired items — `src/pipeline/cleanup.py`
- [x] Source config loader (load candidates; dispatcher fetches only `approved`) — `src/collector/catalog.py` (`seed_candidate_sources`)

### Phase 1f — Deploy ⛔ (未开始)

- [ ] Docker compose on 38 (network_mode: host) — compose 文件就绪，但未 `up`，`:8100` 未监听
- [ ] Smoke test: manual run, verify items + digest
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
2. **装 dev 依赖跑测试** — `make dev` 后 `make test`，确认 15 个测试文件 pass，关闭“测试未运行”的不确定性。
3. **过生产门槛**（§2）— NVIDIA 限流 / Stage1 JSON 输出 / 源可达 / 提升 ≥3 源到 approved / Hexo 写入权限。
4. **补前端**（§3 Phase 1d-front）— 至少补 `styles.css` + 对齐 source ID / stage 字段 / `also_seen_in` 形状。
5. **部署**（§3 Phase 1f）— `docker compose up`（:8100），smoke test，再考虑与旧 `:8900` unified 系统的切换/下线。
