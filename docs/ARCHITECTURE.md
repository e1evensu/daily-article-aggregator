# Intelligence System — 架构设计文档

> 版本: v0.7 | 更新: 2026-05-26
> 状态: **概览草案** — 以 `.spec/` 为准
> 
> 详细设计见 .spec/ 目录。本文档是概览。

---

## 系统架构

```
curated sources (10个, L1 only)
     │
     ▼
collection dispatcher ──→ source health tracking
     │                     (3 failures → disabled)
     ▼
normalize + dedup (cross-source via also_seen_in)
     │
     ▼
Stage 1: deepseek-v4-flash (全量, NVIDIA NIM)
     │
     ├── score < 10 → 立即删
     ├── score < 75 → 设 expires_at
     │
     ▼
Stage 2: deepseek-v4-pro (≥75 分, NVIDIA NIM)
     │   ├── confidence 推导 (tentative → firm → confirmed)
     │   └── trend_signal 赋值 (emerging/growing/stable/declining)
     │
     ▼
digest generation (爬完即生成)
     │
     ├── MySQL: items + digests + runs
     ├── Hexo: digest → /opt/blog/source/_posts/ (主路径)
     ├── OSS: digest markdown backup
     └── REST API (内部, localhost:8100)
```

## 存储

```
38 (EU, 4C8G) — 采集/计算
├── intelligence-api + worker (Docker, network_mode: host)
├── autossh tunnel → 114
└── Hexo posts → /opt/blog/source/_posts/

114 (CN, 4C4G) — 服务机
├── MySQL (Docker, intelligence 库)
├── Redis (Docker)
└── OSS (oss2 SDK, digest 备份)
```

## 4 张核心表

| 表 | 用途 |
|---|---|
| sources | 源配置 + 健康 + domain 枚举 |
| runs | 运行日志 + 各源状态 (JSON) + progress |
| items | 条目 + 内联分析字段 + 保留策略 |
| digests | 日报 + Hexo 路径 + OSS 链接 |

无 channels 表（domain 是枚举）。无 item_analysis 表（合并进 items）。

## 关键设计

- **两段 AI**: flash 全量 → pro 高分 (≥75)，设置 provider-compatible 输出上限，不假设无限额度
- **保守起步**: 10 源 (6 安全 + 4 AI)，质量优先
- **数据分级**: <10 立删 / <30 五天 / <50 十天 / <75 三十天 / ≥75 永久
- **跨源去重**: also_seen_in 记录多源出现，支持 confidence 动态升级
- **Confidence 推导**: tentative (单源) → firm (official 或有交叉源) → confirmed (official+交叉 或 ≥2 交叉源)
- **Trend signal**: emerging / growing / stable / declining，模型判断
- **运行锁**: 同一时间只允许一个 run，12h stale timeout
- **00:00 北京启动**: 爬完分析完就生成日报，不卡固定时间
- **Digest 发布**: Hexo post (主路径) + OSS backup

## API 概览

内部 REST API，bind `127.0.0.1:8100`。

| 端点 | 用途 |
|---|---|
| `GET /api/v1/items` | 条目列表，支持 domain/score/category/confidence 过滤 |
| `GET /api/v1/digests` | 日报，支持 json/markdown 格式 |
| `GET /api/v1/sources` | 源列表，含 health/spark(14天)/today_items |
| `GET /api/v1/runs` | 运行记录，含 progress 和 per-source stats |
| `GET /api/v1/stats` | 聚合统计：histogram、category、confidence、retention |

详见 `.spec/api.md`。

## 前端原型参考

`src/front/` 包含 React CDN 原型（无构建步骤）。它是交互参考，不是 Phase 1 生产 dashboard，也不是数据契约来源。数据契约以 `.spec/data-model.md`、`.spec/source-catalog.md`、`.spec/api.md` 为准。

当前前端原型审查状态：**synced to Phase 1 contract**。

- `styles.css` 已恢复，入口页面不再缺失样式资产。
- Fixture 使用 `.spec/source-catalog.md` 的 canonical long source IDs。
- Fixture 和展示字段使用 `stage1_*` / `stage2_*` 分段分析元数据。
- `also_seen_in` 使用 source occurrence 对象数组 `{source_id,url,seen_at}`。
- Sources 视图将 `status` 与 `health` 分开展示，不把 candidate/trial 当作 approved。
- Digest 视图展示 API contract 中的 `hexo_path` 与 `oss_url`。

| 文件 | 内容 |
|---|---|
| `data.js` | Fixture 数据；需要重新对齐 source catalog、data model、API SPEC |
| `ui.jsx` | 共享组件：ScoreNum/Bar、Confidence、Trend、Health、DomainBadge |
| `view-items.jsx` | Items 列表 + 详情 drawer (Stage 1/2 完整展示) |
| `view-other.jsx` | Digest/Runs/Sources/Stats 视图 |
| `app.jsx` | App shell：sidebar + 导航 + 视图路由 |
| `tweaks-panel.jsx` | 可复用 tweak 控件面板 |

原型目标数据流（待重新校验）：
- domain enum 过滤 + insight_score 排序
- Stage 1/2 分析元数据展示
- also_seen_in 交叉验证展示 ("corroborated by N")
- confidence/trend_signal 仅 Stage 2 展示
- retention 分级可视化
- Run pipeline 步骤进度 (FETCH→NORMALIZE→DEDUP→STAGE1→STAGE2→DIGEST→CLEANUP)
- Source health + 14天 spark 趋势

## Phase 分期

| Phase | 内容 |
|---|---|
| **1** | 10 源 + 两段 AI + 日报 + Hexo + OSS + API (内部) |
| **2** | 飞书推送 + X/Twitter + 实体图谱 + MCP |
| **3** | Dashboard + 金融 + CDP + 用户画像 |

## 修改历史

| 日期 | 版本 | 内容 |
|------|------|------|
| 2026-05-26 | v0.7 | 明确前端原型不是契约来源；记录 fixture/schema/style/source-status 同步问题 |
| 2026-05-26 | v0.6 | 补充 confidence 推导/trend signal 规则、API 概览、前端原型参考、Hexo 发布路径、关闭所有 open questions |
| 2026-05-26 | v0.5 | 与 .spec/ 对齐：砍 channels/source_fetches，加 run lock/also_seen_in/stage-specific analysis metadata，确认基础设施，保留生产运行验证门槛 |

## 注释规范

当前仓库已经补过一轮函数级注释，但后续维护不应继续走“每个函数都机械写一句”的路线。注释规则如下：

### 必须保留注释的地方

- 模块入口、CLI 入口、异步 worker、scheduler、pipeline stage
- API handler、状态机、阈值判断、重试逻辑、并发控制、去重、保留策略
- 有副作用的 helper：写数据库、写文件、发请求、改状态、发事件
- 测试里的 fixture builder、fake session、mock transport、复杂辅助函数

### 可以豁免注释的函数

只有同时满足以下条件时才允许不写：

- 函数体不超过 3 行
- 没有分支
- 没有副作用
- 没有异常语义
- 函数名和类型已经完整表达意图

### 测试代码规则

- `test_*` 函数如果名字已经完整表达行为，可以不写注释
- 非 `test_*` 的测试辅助函数和 fake 类方法，原则上应写注释

### 清理规则

- 保留解释“为什么这样做”“边界是什么”“失败语义是什么”的注释
- 删除纯复述函数名或实现表象的注释
- 模块级说明优先于成批重复的函数说明
