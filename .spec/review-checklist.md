# Review Checklist

> Status: **Updated** — core SPEC aligned; production/frontend gates still open
> Updated: 2026-05-26

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
| NVIDIA rate limit | Test empirically | Implementation |
| HN keyword filter list | Needs definition | Implementation |
| Sub2API fallback | Not tested | Phase 1 or deferred |
| Approved source set | Candidate list exists, approvals pending | Implementation |
| styles.css | 前端原型缺失 styles.css 文件 | 前端 |
| Frontend fixture source IDs | Uses legacy short IDs; must switch to catalog long IDs | 前端 |
| Frontend analysis fields | Uses `analysis_model`/`prompt_version`; must switch to `stage1_*` and `stage2_*` fields | 前端 |
| Frontend `also_seen_in` shape | Uses string array; must use occurrence objects `{source_id,url,seen_at}` | 前端 |
| Source status visibility | API/frontend must expose `candidate/trial/approved`; do not label all sources approved | API/前端 |
| SecHub/aihot 服务部署 | 服务未上线，tunnel 未配置 | 基础设施 |

## 3. Implementation Gate

Scaffolding gate is open:

- [x] Phase 1 scope agreed (security + AI, no dashboard/social/finance)
- [x] Source catalog has candidates (10 sources listed)
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

- [ ] At least 3 sources approved and reachable from 38
- [ ] Stage 1 JSON output tested on sample items
- [ ] NVIDIA rate-limit behavior tested
- [ ] Hexo direct-write path verified (Docker volume mount + permissions)
- [ ] SecHub/aihot tunnel configured (if these sources are needed for first run)

Frontend gate is closed:

- [ ] `src/front/styles.css` exists and page renders without missing assets
- [ ] Fixture source IDs match `.spec/source-catalog.md`
- [ ] Fixture item fields match `.spec/data-model.md` and `.spec/api.md`
- [ ] Sources view displays source `status` separately from health
- [ ] Digest view uses `summary` / `highlights_json` field names

Backend scaffolding can proceed against the SPECs. Scheduled production runs should wait for the production-run gate.
