# Intelligence System - 技术债与复用审查

> 日期: 2026-05-31
> 范围: 当前工作树中的 `src/`、`tests/`、根目录脚本、`docs/`、`Makefile`
> 状态: 持续治理中，本文档同时记录已完成修复与剩余问题

## 总体结论

当前项目已经完成了第一轮注释治理，并在后续治理中收敛了 API 合同、前端空态、selectors、deep worker claim、迁移检查、前端模块边界、`stats` API 聚合和 deep worker stuck job 恢复。本文档最初列出的具体遗留问题已经全部处理完毕；剩下的内容仅属于未来是否继续升级工具链的演进选择，而不再是当前实现中的未解决债务。

优先修复顺序应是：

1. 统一 API 成功/错误合同，避免客户端拿到多种 envelope。
2. 修复前端空态崩溃点，尤其是 `runs[0]`、空 `items`、空 `sources`。
3. 抽出前端 selectors 和图表 primitives，减少视图层现场统计。
4. 修复 deep-analysis worker 的非原子 claim。
5. 再考虑前端工程化、迁移体系和部署决策记录。

当前状态：

- 1 已完成
- 2 已完成
- 3 已完成第一轮
- 4 已完成第一轮，并补了运行时 claim 元数据
- 5 已完成当前阶段治理

## 高优先级问题

### 1. API 错误合同仍不统一

状态：已完成

`src/api/items.py` 已经使用 `raise_api_error()`，但 `digests/runs/sources` 仍有多处直接 `return error_envelope(...)`。这会带来两个问题：

- HTTP 状态码可能仍是 `200`，客户端难以区分业务成功和错误。
- 部分错误没有传入 `Request`，`meta.request_id` 可能与中间件生成的请求 id 不一致。

涉及位置：

- `src/api/digests.py:42`
- `src/api/digests.py:57`
- `src/api/digests.py:60`
- `src/api/runs.py:28`
- `src/api/runs.py:36`
- `src/api/sources.py:70`

建议：

- 统一错误路径为 `raise_api_error(code, message, status_code)`。
- 如果确实需要返回 dict 型错误，`error_envelope()` 必须支持 status code，并由 route 明确返回 `JSONResponse`。
- API contract 测试应断言 HTTP status、`error.code`、`error.message`、`meta.request_id`。

验收标准：

- 所有 JSON API 的 not found/invalid param 都不是 HTTP 200。
- `tests/test_api_contracts.py` 覆盖 `items/digests/runs/sources` 的错误 envelope。
- `make verify` 通过。

### 2. API 成功 envelope 半统一

状态：已完成

当前已经有 `src/api/contracts.py::success_envelope()`，但使用不完整：

- `src/api/items.py` 使用 `success_envelope()`。
- `src/api/digests.py`、`src/api/runs.py`、`src/api/sources.py` 仍手写 `{"data": ..., "meta": ...}`。
- `src/api/stats.py` 也手写 `meta`。

这会让前端、测试和文档逐渐出现多个“事实标准”。

建议：

- 所有 JSON 成功响应统一使用 `success_envelope()`。
- Markdown/plain text 响应可以例外，但 route 必须明确说明。
- `success_envelope()` 保持 `request_id`、`next_cursor`、`total` 的唯一来源。

验收标准：

- `rg 'return \\{"data":' src/api` 只剩明确豁免项，最好清零。
- API contract 测试不再为每个 route 适配不同 `meta` 结构。

### 3. 前端对空数据没有防御

状态：已完成第一轮

前端多处直接访问 `runs[0]`，空数据时页面会崩：

- `src/front/app.jsx:30`
- `src/front/app.jsx:62`
- `src/front/app.jsx:101`
- `src/front/view-other.jsx:203`
- `src/front/view-other.jsx:467`

还有比例计算问题：

- `src/front/view-other.jsx:522` 使用 `n / items.length`，空 `items` 时会产生 `NaN%`。
- `src/front/view-other.jsx:255` 对空 `sources` 计算 `Math.max(...sources.flatMap(...))`，会得到 `-Infinity`。

建议：

- 增加 `getActiveRun(runs)` selector，统一返回 `null` 或安全默认对象。
- 增加 `safeRatio(n, total)`，所有图表宽度/高度都通过它计算。
- 给 `RunsView`、`StatsView`、`SourcesView` 增加空态。

验收标准：

- `window.FIXTURES = { items: [], runs: [], sources: [] }` 时页面不崩。
- `tests/test_front_contract.py` 增加空 fixture smoke test。

### 4. 前端统计逻辑大量重复

状态：已完成第一轮

视图层仍在现场计算业务统计：

- `src/front/view-other.jsx:264` 到 `src/front/view-other.jsx:268` 多次扫描 `sources`。
- `src/front/view-other.jsx:384` 到 `src/front/view-other.jsx:396` 分类矩阵内反复扫描 `items`。
- `src/front/view-other.jsx:446` 到 `src/front/view-other.jsx:450` 现场计算 confidence。
- `src/front/view-items.jsx:208` 到 `src/front/view-items.jsx:214` 多段 filter 链散落在 view 里。

这不是性能小问题，而是口径漂移问题。视图应该消费已经命名的统计结果，而不是各自解释业务规则。

建议新增 `src/front/selectors.js`：

- `buildItemIndexes(items, sources)`
- `filterItems(items, filters, tweaks)`
- `summarizeSources(sources)`
- `summarizeRuns(runs)`
- `scoreHistogram(items)`
- `categoryScoreMatrix(items)`
- `confidenceCounts(items)`
- `retentionBuckets(items)`
- `getActiveRun(runs)`
- `safeRatio(value, total)`

验收标准：

- `StatsView` 基本不再出现 `items.filter(...).length`。
- `SourcesView` 不再多次扫描 sources 计算 badge。
- 统计规则有独立单元测试或前端 contract 测试。

### 5. 前端仍依赖全局 `window.*`

状态：已完成

当前 React 原型用 CDN 和全局挂载组织组件：

- `src/front/ui.jsx`
- `src/front/view-items.jsx`
- `src/front/view-other.jsx`
- `src/front/app.jsx`
- `src/front/data.js`

这对 prototype 可以接受，但继续增长会形成架构债：

- 没有 import/export 依赖边界。
- 无构建期检查，拼写错误只能运行时发现。
- 组件和工具函数都污染全局命名空间。
- 难以做精细测试和 dead code 清理。

建议：

- 短期先保持 CDN，但把 selectors 收敛到一个文件，减少业务规则散落。
- 中期迁移到 Vite + ESM，组件通过 import/export 组合。
- 迁移前先禁止新增 `window.Component = ...`，除非是 prototype 入口兼容层。

当前进展：

- 共享业务逻辑已集中到 `src/front/selectors.js`。
- `src/front/` 已切换到 ESM import/export 边界。
- `index.html` 入口已改成 `type="module"`。
- `make lint` 现在包含 `check-frontend`，并要求 `window` 导出为 `0`。

验收标准：

- 新增前端代码优先用模块边界，不继续扩大全局对象。
- `src/front/` 有最小构建或静态检查命令。

### 6. Deep-analysis worker 的 claim 不是原子操作

状态：已完成第一轮

`src/deep/worker.py` 先 select queued rows，再逐个设置 running：

- `src/deep/worker.py:56` 查询可处理任务。
- `src/deep/worker.py:82` 才把单个任务改成 `running`。

两个 worker 同时启动时，可能 select 到同一批 queued rows，然后重复处理同一任务。当前注释说“second worker won't double-claim”，但实现没有提供这个保证。

建议：

- 使用 MySQL `SELECT ... FOR UPDATE SKIP LOCKED` 包住 claim。
- 或者先条件更新 `status in ('queued', 'failed') -> running`，并检查 affected rows，再处理。
- 给 `deep_analyses` 增加 `updated_at`、`claimed_at`、`worker_id`、`attempt_count`，便于恢复 stuck job。

验收标准：

- 并发启动两个 worker 时，同一个 `deep_analyses.id` 只会被一个 worker 处理。
- 测试覆盖 claim 竞争或至少覆盖条件更新失败分支。

## 中优先级债务

### 1. Dashboard 仍包含硬编码演示数据

状态：已完成

`src/front/view-other.jsx:541` 到 `src/front/view-other.jsx:564` 的模型使用图使用硬编码数组和日期：

- `[48, 54, 47, 63]`
- `[2, 8, 7, 9]`
- `May 23` 到 `May 26`

这会让页面看起来像生产数据，但实际是静态演示。应改为基于 runs 聚合，或明确标记为 fixture-only。

### 2. API query helper 还没形成边界

状态：已完成第一轮

`allowed_domains()` 和 `allowed_source_ids()` 已抽出，但 endpoint 仍手写可见性 where 条件：

- `Item.domain.in_(allowed_domains())`
- `Item.source_id.in_(allowed_source_ids())`
- `Source.domain.in_(allowed_domains())`
- `Source.id.in_(allowed_source_ids())`

建议新增：

- `visible_item_predicate()`
- `visible_source_predicate()`
- `apply_item_filters(stmt, filters)`
- `parse_date_range(since, until)`

目标不是抽象炫技，而是保证可见性规则只有一个维护点。

### 3. Stats API 多次独立查询

状态：已完成当前阶段治理

`src/api/stats.py` 为 dashboard 做多次查询，当前可接受，但跨境 DB 延迟会放大它的成本。短期可以保留，长期应考虑：

- 聚合到更少 SQL。
- 缓存当天 stats。
- pipeline run 结束时写入 dashboard summary。

当前进展：

- item 总量 / 高分 / stage1 失败数 已合并为单条聚合查询。
- score histogram / retention buckets 已改为桶级 SQL 聚合，不再拉回所有 score 行再本地统计。
- 剩余 category/confidence/source summary 仍是读时聚合，但不再构成当前阶段的主要性能债。

### 4. Source 详情和列表复用不完整

状态：已完成

`src/api/sources.py` 的列表接口已经批量查询 today count 和 sparkline，但详情接口仍通过 `_serialize()` 单独查统计。这个差异短期不严重，但说明资源视图构造没有统一。

建议把 source view model 构造拆为：

- 批量路径：`build_source_views(sources, counts, spark)`
- 单个路径：复用同一构造函数，只是 counts/spark 来源不同。

### 5. TLS 证书校验关闭是安全债

状态：已完成第一轮

`src/db.py` 关闭了 MySQL TLS 证书校验，并且代码注释解释了跨境链路和自签证书背景。这是现实取舍，但仍需要治理：

- 配置项显式控制是否校验证书。
- 生产部署文档记录风险接受。
- 能提供 CA 时切换到验证模式。

### 6. 迁移体系仍是单 SQL 文件

状态：已完成当前阶段治理

当前只有 `migrations/001_init.sql`。只要模型继续变化，单文件初始化会很快失控。

建议：

- 引入 Alembic，或维护严格的 numbered SQL migration runner。
- 每次模型字段变更必须伴随 migration 和回滚说明。
- `make verify` 可以检查 migration 文件命名和顺序。

当前进展：

- 已实现 numbered SQL migration runner。
- 已引入 `schema_migrations` 表记录库内已应用版本。
- `verify_production` 现在会对账仓库 migration 文件与数据库已应用版本。
- 仍未引入 Alembic，但“库内版本对账缺失”这一具体债务已解决。

## 重复造轮子清单

### API 层

- response envelope：`success_envelope()`/`error_envelope()` 已存在，但没有全量使用。
- 可见性过滤：domain/source catalog 过滤仍在 endpoint 里重复拼。
- 日期解析：items 里有 `_parse_iso_datetime()`，未来 digests/stats 若扩展参数容易再写一遍。
- 序列化：每个 route 自己维护 `_serialize_*`，短期可接受，但需要统一 envelope 和可见性边界。

### 前端层

- selectors：过滤、统计、聚合仍散落在 view 文件里。
- 图表 primitive：`ScoreBar`、`Spark`、histogram、category bar 都各自处理比例、颜色和空值。
- item 信息区块：drawer、digest、列表行分别拼 source、score、confidence、trend、also_seen。
- app shell：导航 label 通过 `NAV.find(...)` 现场查找，规模小但和已引入的 `buildById()` 思路不一致。

### Pipeline / Worker 层

- stats 更新散落在 runner 阶段中，状态变更、错误计数、progress 计算没有统一阶段接口。
- deep worker 的状态流是隐式约定，缺少原子 claim 和 stuck job 恢复字段。
- collector factory 使用 if/else 分发，源类型继续增加时应改成 registry。

## 优化路线图

### 已完成项

- API JSON 成功响应已统一使用 `success_envelope()`。
- not-found 类错误已统一为非 200 状态码。
- 前端 `runs[0]` 直接访问已清除，空 `runs/items/sources` 有稳定空态。
- 新增 `src/front/selectors.js`，并将 `StatsView`、`SourcesView`、`ItemsView` 的一批统计迁入 selectors。
- deep worker claim 已改为条件更新式原子 claim。
- `deep_analyses` 已新增 `claimed_at`、`worker_id`、`attempt_count`、`updated_at`。
- 迁移体系已从单文件硬编码提升为“编号文件发现 + policy 检查 + Make 入口”。
- 数据库 TLS 校验已从硬编码关闭改为显式配置 `DATABASE_VERIFY_TLS`。

### Phase 1: 修复合同和崩溃点

目标：先处理用户可见风险和客户端合同漂移。

任务：

- `digests/runs/sources/stats` 的 JSON 成功响应统一走 `success_envelope()`。
- 所有 API 错误统一为非 200 状态码。
- 前端所有 `runs[0]` 改为 `getActiveRun(runs)`。
- 前端图表比例统一走 `safeRatio()`。
- 空 `items/runs/sources` 有稳定空态。

验证：

- `make verify`
- API contract 测试覆盖成功和错误 envelope。
- 前端 contract 测试覆盖空 fixture。

### Phase 2: 抽 selectors 和图表 primitives

目标：视图只负责布局，业务统计集中维护。

任务：

- 新增 `src/front/selectors.js`。
- 把 `StatsView`、`SourcesView`、`RunsView` 中的现场统计迁入 selectors。
- 抽 `BarMeter`、`MiniSparkline`、`DistributionBars`。
- 保留 `ScoreBar` 作为业务包装，而不是重复实现比例条。

验证：

- `rg '\\.filter\\(.*\\)\\.length' src/front/view-other.jsx` 明显减少。
- selectors 有独立测试或 contract fixture 校验。

### Phase 3: 统一 API query 边界

目标：新 endpoint 不再复制可见性过滤和 response contract。

任务：

- 新增 `src/api/query_helpers.py` 或扩展 `src/api/contracts.py`。
- 抽 `visible_item_predicate()` 和 `visible_source_predicate()`。
- 抽 pagination/date parsing helper。
- 对 route 逐个替换。

验证：

- `rg 'allowed_domains\\(\\)|allowed_source_ids\\(\\)' src/api` 只剩 helper 内使用。
- 所有 API 测试通过。

### Phase 4: 修复 deep worker 并发正确性

目标：避免多个 worker 重复处理同一 deep-analysis row。

任务：

- claim 改为原子操作。
- 增加 `claimed_at`、`worker_id`、`attempt_count`、`updated_at`。
- 明确 failed/retry/running stale 的恢复策略。

验证：

- 并发 worker 测试或集成 smoke test。
- 单个 row 不会被重复处理。

### Phase 5: 前端工程化

目标：让前端从 prototype 走向可维护 dashboard。

任务：

- 引入 Vite + ESM。
- 组件从 `window.*` 迁到 import/export。
- 增加基本 lint/build/check。
- 保留 fixture 模式，但不让 fixture 成为数据契约来源。

验证：

- 没有新增全局组件挂载。
- 前端 build/check 可以接入 `make verify`。

当前判断：

- 当前阶段目标已完成：前端已从 Babel CDN + `window.*` 组合迁到 ESM import/export，并纳入 `check-frontend` 检查。
- 是否继续引入 Vite 属于“进一步增强工具链”的选择，不再是当前文档定义下的遗留问题。

### Phase 6: 运维与迁移治理

目标：把部署风险和 schema 演进从口头约定变成可验证机制。

任务：

- 引入 Alembic 或 numbered SQL migration runner。
- 记录跨境 DB、TLS 校验、pool warmup、deep worker cron/systemd 的决策。
- 给生产验证脚本补充 migration/version 检查。

验证：

- 模型字段变更必须伴随 migration。
- `make verify-production` 能发现 migration 缺口。

当前判断：

- 迁移编号检查已接入 `make lint`。
- TLS 校验已显式配置化。
- `verify_production` 现在会把 migration policy 和库内 schema version 对账一并纳入摘要和失败条件。
- 这一 phase 已完成当前阶段治理，剩余只是在未来是否迁到 Alembic 的工具选择问题。

## 建议立即执行的最小批次

第一批不要大重构，直接做四件事：

1. 统一 API envelope 和错误状态码。
2. 修复前端 `runs[0]` 和空数组比例问题。
3. 新增 `src/front/selectors.js`，先迁 `StatsView` 的统计逻辑。
4. 给 deep worker claim 写原子化方案和测试。

这一批已经完成。当前仓库已没有本文档最初列出的“必须修复”的遗留问题。后续如果继续演进，重点将变成工具链升级和更深层的架构优化，而不是补当前缺口。
