下面按代码路径拆解。先给结论：Horizon 是一个“统一数据模型 + 显式装配的 scraper 集合 + 分阶段 AI 流水线 + 双入口（CLI/MCP）复用”的架构。CLI 从 [src/main.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/main.py:34) 进入，MCP 从 [src/mcp/server.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/mcp/server.py:15) / [src/mcp/service.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/mcp/service.py:43) 进入，但两者都回到同一套 `src/models.py`、`src/orchestrator.py`、`src/ai/*`、`src/storage/*`。

**1) scraper 插件体系**
- 这个体系更像“显式注册的适配器集合”，不是自动发现式插件。基类在 [src/scrapers/base.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/scrapers/base.py:11)，只规定 `config`、共享 `httpx.AsyncClient`、抽象 `fetch(since)`，以及统一的 `_generate_id()`。
- 真正的注册点在 [src/orchestrator.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/orchestrator.py:228) 的 `fetch_all_sources()`：根据 `config.sources.*` 显式实例化各 scraper，再 `asyncio.gather` 并发拉取；没有 entry-point 自动发现，也没有统一 factory。
- 生命周期很短：`async with httpx.AsyncClient(...)` -> 构造 scraper -> `fetch()` -> 返回 `List[ContentItem]` -> client 退出即销毁；scraper 本身不保留跨 run 状态。
- 扩展一个新源，通常要同时改 `src/models.py` 的配置模型、写新的 scraper 文件、在 `orchestrator.py` 加分支；如果要让 MCP 的源过滤也识别它，还要改 `src/mcp/horizon_adapter.py` 的白名单。
- 各实现模式很一致，但“取数策略”不同：`GitHubScraper` 走事件/Release API，`HackerNewsScraper` 走 topstories + comments，`RSSScraper` 走 feedparser，`RedditScraper` 走 Reddit JSON + 评论并发，`TelegramScraper` 解析网页 HTML，`TwitterScraper` 通过 Apify 跑任务/轮询 dataset，`OpenBBScraper` 包一层同步 SDK，`OSSInsightScraper` 拉趋势 API。

对应实现可看这些文件：
`[src/scrapers/github.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/scrapers/github.py:15)`
`[src/scrapers/hackernews.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/scrapers/hackernews.py:19)`
`[src/scrapers/rss.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/scrapers/rss.py:20)`
`[src/scrapers/reddit.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/scrapers/reddit.py:31)`
`[src/scrapers/telegram.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/scrapers/telegram.py:21)`
`[src/scrapers/twitter.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/scrapers/twitter.py:23)`
`[src/scrapers/openbb.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/scrapers/openbb.py:42)`
`[src/scrapers/ossinsight.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/scrapers/ossinsight.py:19)`

**2) orchestrator 如何编排完整流程**
- 主编排入口是 [src/orchestrator.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/orchestrator.py:50) 的 `run()`，顺序基本是：时间窗 -> 采集 -> exact 去重 -> AI 打分 -> 阈值过滤 -> 语义去重 -> 可选 Twitter 讨论扩展 -> 富化 -> 生成日报 -> 推送。
- exact 去重在 [src/orchestrator.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/orchestrator.py:338)：按归一化 URL 分组，保留 `content` 最长的 primary，合并 metadata 和其他来源的内容，最后写入 `merged_sources`。
- 语义去重在 [src/orchestrator.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/orchestrator.py:394)：先按 `ai_score` 排序，再把 `title/tags/summary` 发给 LLM，让模型返回 duplicates 索引组，primary 永远是组内第一个高分项。
- Twitter 的二次扩展是一个特殊旁路，[src/orchestrator.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/orchestrator.py:467) 里会抓 reply 文本并把它拼回 `content`，然后对这些 item 重新跑一遍 analyzer。
- “推送”不是单一通道，而是多 sink：先写 `data/summaries/`，再复制到 `docs/_posts/`，然后按配置发 email / webhook；所以日报既是产物，也是分发源。

**3) AI 分析管线如何链式协作**
- AI 客户端是抽象出来的，`create_ai_client()` 在 [src/ai/client.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/ai/client.py) 按 provider 选择 Anthropic / OpenAI 兼容 / Azure / Gemini，实现细节都收在这里，分析器和富化器都只依赖 `AIClient` 接口。
- `ContentAnalyzer` 在 [src/ai/analyzer.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/ai/analyzer.py:18) 做第一段 LLM：它把标题、内容、评论、engagement metadata 组装成 prompt，要求模型只回 JSON，然后把结果写回 `ContentItem.ai_score / ai_reason / ai_summary / ai_tags`。
- `ContentEnricher` 在 [src/ai/enricher.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/ai/enricher.py:27) 做第二段 LLM：先让模型抽取 1-3 个概念查询词，再用 DuckDuckGo 搜索，最后让模型基于搜索结果生成双语结构化字段，写入 `metadata`。
- 严格说，`DailySummarizer` 并不是第三段 LLM，它是纯渲染器，在 [src/ai/summarizer.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/ai/summarizer.py:64) 把 analyzer/enricher 的结果拼成 Markdown 日报；也就是说真正的链条是“打分 -> 过滤 -> 富化 -> 渲染”。
- 这条链是成本分层的：打分覆盖全量，富化只跑高分项，摘要只消费结构化结果；异常时 analyzer 会降级成 0 分，enricher 会跳过富化，整体是 best-effort。

**4) `ContentItem` 的字段含义**
定义在 [src/models.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/models.py:22)。
- `id`：全局唯一键，格式是 `{source}:{subtype}:{native_id}`。
- `source_type`：来源枚举，区分 GitHub/HN/RSS/Reddit/Telegram/Twitter/OpenBB/OSSInsight。
- `title`：原始标题或 scraper 合成标题。
- `url`：规范化后的主链接。
- `content`：正文、评论、讨论文本，或抽取后的可分析文本。
- `author`：发布者 / 账号 / 频道名。
- `published_at`：原始发布时间。
- `fetched_at`：抓取时间，默认 UTC 现在。
- `metadata`：源特定字段和富化结果的容器。
- `ai_score`：0-10 的重要性分。
- `ai_reason`：打分理由。
- `ai_summary`：一行摘要，供去重和渲染使用。
- `ai_tags`：主题标签。

这个模型的关键设计是：`ai_*` 保持很少的强结构字段，其他扩展信息都落进 `metadata`，所以每个 scraper 可以自由带自己的上下文，不会把主模型撑爆。

**5) Config 配置体系的层次结构**
顶层模型在 [src/models.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/models.py:319)，实际 JSON 形状也和 `data/config.example.json` 一一对应。
```text
Config
├─ version
├─ ai: AIConfig
│  ├─ provider / model / base_url / api_key_env
│  ├─ temperature / max_tokens / throttle_sec
│  ├─ analysis_concurrency / enrichment_concurrency
│  ├─ languages
│  └─ azure_endpoint_env / api_version
├─ sources: SourcesConfig
│  ├─ github: list[GitHubSourceConfig]
│  ├─ hackernews: HackerNewsConfig
│  ├─ rss: list[RSSSourceConfig]
│  ├─ reddit: RedditConfig
│  ├─ telegram: TelegramConfig
│  ├─ twitter?: TwitterConfig
│  ├─ openbb?: OpenBBConfig
│  └─ ossinsight: OSSInsightConfig
├─ filtering: FilteringConfig
├─ email?: EmailConfig
└─ webhook?: WebhookConfig
```
- 配置是“环境变量 + JSON + Pydantic 校验”的三层结构：`StorageManager.load_config()` 会先递归展开 `${VAR}`，再 `Config.model_validate()`。
- webhook 有一组显式枚举校验：`delivery/platform/layout/fallback_layout/overview_position` 都被约束成有限集合。
- `ai.languages` 会直接驱动日报生成的语言循环；`filtering.ai_score_threshold` 和 `time_window_hours` 则控制整条流水线的门槛和时间窗。

**6) MCP Server 的工具暴露方式和与主管线的复用**
- 入口在 [src/mcp/server.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/mcp/server.py:15)，用 `FastMCP` 暴露工具和资源；工具层是 `@mcp.tool()`，资源层是 `@mcp.resource()`。
- 工具分成三类：配置校验、阶段操作、端到端运行。最核心的是 `hz_fetch_items / hz_score_items / hz_filter_items / hz_enrich_items / hz_generate_summary / hz_run_pipeline`，外加 `hz_list_runs / hz_get_run_* / hz_get_metrics / hz_send_webhook`。
- `HorizonPipelineService` 在 [src/mcp/service.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/mcp/service.py:43) 不是重写业务逻辑，而是把主管线切成可重入的 stage：`fetch_items -> score_items -> filter_items -> enrich_items -> generate_summary`。
- 复用的关键在 [src/mcp/horizon_adapter.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/mcp/horizon_adapter.py:109)：它动态 import 本地 Horizon 源码，构造 `HorizonRuntime`，然后直接复用 `HorizonOrchestrator`、`ContentAnalyzer`、`ContentEnricher`、`DailySummarizer`、`StorageManager`。
- MCP 的中间态由 [src/mcp/run_store.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/mcp/run_store.py:24) 管，artifact 落在 `data/mcp-runs/<run_id>/`，文件分为 `raw/scored/filtered/enriched` 和 `summary-<lang>.md`，便于断点续跑和审计。
- 资源是只读快照，`horizon://runs/{run_id}/items/{stage}`、`horizon://runs/{run_id}/summary/{language}`、`horizon://config/effective` 都是 inspection 用。
- 一个值得注意的差异：`horizon_adapter.py` 的 `VALID_SOURCES` 当前没把 `ossinsight` 放进 MCP 白名单，所以 CLI 支持的这个源在 MCP 的 `sources` 过滤里不会被选中。

**7) `StorageManager` 的设计**
- `StorageManager` 在 [src/storage/manager.py](/home/suuuu/develop/intelligence-system/archive/Horizon/src/storage/manager.py:53) 只管应用级持久化：配置、最终摘要、订阅者列表。
- 初始化时只做两件事：创建 `data_dir` 和 `data/summaries`。
- `load_config()` 的流程是：读 `config.json` -> 展开 `${VAR}` -> Pydantic 校验；这和 MCP 适配层的加载策略是同一套。
- `save_config()` 会在覆盖前备份成 `config.json.bak`；`save_daily_summary()` 则把 Markdown 写成 `data/summaries/horizon-<date>-<lang>.md`。
- `load_subscribers/add_subscriber/remove_subscriber` 管的是 `subscribers.json`，属于 email 分发配套状态。
- 需要区分的是：`StorageManager` 不是 MCP 的 stage store；MCP 的中间产物由 `RunStore` 单独管理，这样应用配置/最终结果和中间阶段不会混在一起。

一句话总结：Horizon 的核心不是“一个大程序”，而是“统一模型 + 显式 scraper 装配 + 两段 LLM + 纯渲染摘要 + CLI/MCP 双入口复用”，所以它的可扩展性主要来自清晰的阶段边界，而不是复杂的框架抽象。