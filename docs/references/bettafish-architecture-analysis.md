下面按你列的 7 个重点梳理。一个关键先说明：当前代码里没有 `langgraph` 依赖，也没有 `StateGraph/add_node/add_edge/compile` 这类实现；`InsightEngine` 是“节点类 + 状态对象 + 手写调度循环”的 agent 工作流，而不是实际 LangGraph 实现。

**1. MindSpider 爬虫系统**

MindSpider 的总入口在 [MindSpider/main.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/MindSpider/main.py)。`MindSpider.run_complete_workflow()` 串联两步：

1. `run_broad_topic_extraction()`：先做宽泛热点话题发现。
2. `run_deep_sentiment_crawling()`：再用这些关键词做多平台深度爬取。

BroadTopicExtraction 位于 [MindSpider/BroadTopicExtraction/main.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/MindSpider/BroadTopicExtraction/main.py)，核心数据流是：

`NewsCollector.collect_and_save_news()`  
→ `TopicExtractor.extract_keywords_and_summary()`  
→ `DatabaseManager.save_daily_topics()`  
→ `daily_news/daily_topics`

工作方式：

- [get_today_news.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/MindSpider/BroadTopicExtraction/get_today_news.py) 的 `NewsCollector` 从 `https://newsnow.busiyi.world/api/s?id={source}&latest` 抓取热榜，源包括微博、知乎、B站、头条、抖音、GitHub Trending、雪球等。
- `_process_news_item()` 把不同热榜统一成 `{id,title,url,source,rank}`。
- [database_manager.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/MindSpider/BroadTopicExtraction/database_manager.py) 的 `save_daily_news()` 以“按日期覆盖”模式写入 `daily_news`。
- [topic_extractor.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/MindSpider/BroadTopicExtraction/topic_extractor.py) 的 `TopicExtractor` 用 OpenAI-compatible LLM 从热榜标题中生成 JSON：`keywords + summary`。
- `save_daily_topics()` 写入 `daily_topics`，其中 `topic_id = summary_YYYYMMDD`，`keywords` 以 JSON 字符串保存。

DeepSentimentCrawling 位于 [MindSpider/DeepSentimentCrawling/main.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/MindSpider/DeepSentimentCrawling/main.py)，核心数据流是：

`KeywordManager.get_latest_keywords()`  
→ `PlatformCrawler.run_multi_platform_crawl_by_keywords()`  
→ MediaCrawler 子模块  
→ 平台内容表和评论表

工作方式：

- [keyword_manager.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/MindSpider/DeepSentimentCrawling/keyword_manager.py) 从 `daily_topics.keywords` 取关键词；如果当天没有，就回退最近 7 天；再没有就用默认关键词。
- 当前实现不是“平台差异化分配关键词”，而是“所有平台使用同一组关键词”。`get_all_keywords_for_platforms()` 和 `get_keywords_for_platform()` 都返回同源关键词。
- [platform_crawler.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/MindSpider/DeepSentimentCrawling/platform_crawler.py) 动态改写 MediaCrawler 的 `config/db_config.py` 和 `config/base_config.py`，设置 `PLATFORM`、`KEYWORDS`、`CRAWLER_TYPE="search"`、`SAVE_DATA_OPTION`、`ENABLE_GET_COMMENTS=True` 等。
- 然后通过 `subprocess.run([sys.executable, "main.py", "--platform", platform, ...], cwd=MediaCrawler)` 启动子模块爬虫。
- 支持平台是 `xhs/dy/ks/bili/wb/tieba/zhihu`，数据最后落到 `xhs_note`、`douyin_aweme`、`bilibili_video`、`weibo_note` 等大数据表。

简言之：BroadTopicExtraction 是“外部热榜 → 今日关键词”，DeepSentimentCrawling 是“今日关键词 → 社媒内容/评论沉淀”。

**2. InsightEngine agent 工作流**

InsightEngine 主体在 [InsightEngine/agent.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/InsightEngine/agent.py)。它没有 LangGraph 运行图，而是 `DeepSearchAgent.research()` 手写流程：

`_generate_report_structure(query)`  
→ `_process_paragraphs()`  
→ 每个段落 `_initial_search_and_summary()`  
→ `_reflection_loop()`  
→ `_generate_final_report()`  
→ `_save_report()`

节点设计：

- [nodes/base_node.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/InsightEngine/nodes/base_node.py)：定义 `BaseNode.run()`、`validate_input()`、`process_output()`；`StateMutationNode` 额外定义 `mutate_state()`。
- [nodes/report_structure_node.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/InsightEngine/nodes/report_structure_node.py)：`ReportStructureNode` 根据 query 让 LLM 输出段落结构，并写入 `State.paragraphs`。
- [nodes/search_node.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/InsightEngine/nodes/search_node.py)：`FirstSearchNode` 和 `ReflectionNode` 负责生成 `search_query/reasoning`。但它们当前 `process_output()` 只稳定返回 `search_query` 和 `reasoning`，agent 里虽读取 `search_tool`，节点解析逻辑并未显式保留该字段，这是一个代码与提示词意图可能不完全一致的点。
- [nodes/summary_node.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/InsightEngine/nodes/summary_node.py)：`FirstSummaryNode` / `ReflectionSummaryNode` 根据搜索结果生成或更新 `paragraph.research.latest_summary`。这里还会读取 `logs/forum.log` 中最新 HOST 发言注入 prompt。
- [nodes/formatting_node.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/InsightEngine/nodes/formatting_node.py)：`ReportFormattingNode` 把各段落汇总成 Markdown 报告。

状态管理在 [InsightEngine/state/state.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/InsightEngine/state/state.py)：

- `State`：保存 `query/report_title/paragraphs/final_report/is_completed`。
- `Paragraph`：保存段落标题、计划内容、顺序、`Research`。
- `Research`：保存 `search_history/latest_summary/reflection_iteration/is_completed`。
- `Search`：保存每次查询结果的 `query/url/title/content/score/timestamp`。

工具集成在 [InsightEngine/tools/search.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/InsightEngine/tools/search.py)：

- `MediaCrawlerDB` 封装本地舆情数据库查询。
- 工具包括 `search_hot_content`、`search_topic_globally`、`search_topic_by_date`、`get_comments_for_topic`、`search_topic_on_platform`。
- `InsightEngine/agent.py` 的 `execute_search_tool()` 又叠加两层中间件：
  - [tools/keyword_optimizer.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/InsightEngine/tools/keyword_optimizer.py)：把 LLM 生成的偏正式查询转换成网民真实会使用的关键词。
  - `multilingual_sentiment_analyzer`：对查询结果或热点内容做情感分析。
- 查询结果多时会用 `SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2") + KMeans` 做聚类采样，避免 prompt 被重复内容淹没。

**3. ReportEngine 报告生成管线**

ReportEngine 是全系统最完整的生成管线，主入口在 [ReportEngine/agent.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/ReportEngine/agent.py) 的 `ReportAgent.generate_report()`。

整体流程：

`模板选择`  
→ `模板切片`  
→ `文档布局设计`  
→ `章节字数规划`  
→ `逐章生成 Chapter JSON`  
→ `Document IR 装订`  
→ `HTMLRenderer 渲染`  
→ `HTML/IR/State 落盘`

关键组件：

- [nodes/template_selection_node.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/ReportEngine/nodes/template_selection_node.py)：扫描 `ReportEngine/report_template/*.md`，让 LLM 根据 Query/Media/Insight 三份报告和论坛日志选择模板。
- [core/template_parser.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/ReportEngine/core/template_parser.py)：`parse_template_sections()` 用正则解析 Markdown 标题、列表、编号，生成 `TemplateSection`，并分配稳定 `chapter_id=S1/S2/...`。
- [nodes/document_layout_node.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/ReportEngine/nodes/document_layout_node.py)：生成全局标题、目录、Hero、主题 token。
- [nodes/word_budget_node.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/ReportEngine/nodes/word_budget_node.py)：生成 `totalWords/globalGuidelines/chapters`，为每章设置目标字数和重点。
- [nodes/chapter_generation_node.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/ReportEngine/nodes/chapter_generation_node.py)：逐章调用 LLM 输出结构化 Chapter JSON；使用 `IRValidator` 校验，失败后会本地修复、跨引擎 LLM 修复，必要时生成占位章节。
- [core/stitcher.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/ReportEngine/core/stitcher.py)：`DocumentComposer.build_document()` 把章节按 `order` 排序，补全 anchor，生成整本 Document IR。
- [renderers/html_renderer.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/ReportEngine/renderers/html_renderer.py)：`HTMLRenderer.render(document_ir)` 把 IR 渲染成完整 HTML，内置 Chart.js/MathJax/html2canvas/jsPDF 依赖和图表校验修复逻辑。

模板目录是 [ReportEngine/report_template](/home/suuuu/develop/intelligence-system/archive/BettaFish/ReportEngine/report_template)，包含日常监测、突发危机、企业品牌、市场竞争、政策行业、社会热点等模板。

Flask 接口在 [ReportEngine/flask_interface.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/ReportEngine/flask_interface.py)，提供 `/api/report/status`、`/api/report/generate`、SSE 流式事件、任务历史、日志转发等。

**4. QueryEngine 与 MediaEngine**

这两个引擎共享几乎相同的 agent 骨架：`DeepSearchAgent.research()` 生成结构、逐段搜索、反思、汇总、格式化。差异主要在检索工具。

QueryEngine：

- 主入口：[QueryEngine/agent.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/QueryEngine/agent.py)
- 工具：[QueryEngine/tools/search.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/QueryEngine/tools/search.py)
- 职责：偏“实时网页/新闻信息检索”。
- 使用 `TavilyNewsAgency`，工具包括：
  - `basic_search_news`
  - `deep_search_news`
  - `search_news_last_24_hours`
  - `search_news_last_week`
  - `search_images_for_news`
  - `search_news_by_date`
- 输出是 Markdown 报告，保存到 `query_engine_streamlit_reports`。

MediaEngine：

- 主入口：[MediaEngine/agent.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/MediaEngine/agent.py)
- 工具：[MediaEngine/tools/search.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/MediaEngine/tools/search.py)
- 职责：偏“多模态/结构化信息搜索”。
- 默认使用 `BochaMultimodalSearch`，可用 `AnspireSearchAgent` 切到 Anspire。
- Bocha 工具包括：
  - `comprehensive_search`
  - `web_search_only`
  - `search_for_structured_data`
  - `search_last_24_hours`
  - `search_last_week`
- `BochaResponse` 不只含网页，还含 `images/modal_cards/follow_ups/answer`，适合补充报告里的图片、模态卡、结构化资料。

三者定位可以概括为：

- QueryEngine：外网新闻和实时事实。
- MediaEngine：多模态和结构化外部资料。
- InsightEngine：本地社媒舆情数据库和情感分析。

**5. 数据库 Schema**

核心 schema 在 [MindSpider/schema/models_sa.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/MindSpider/schema/models_sa.py)，平台大表在 [MindSpider/schema/models_bigdata.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/MindSpider/schema/models_bigdata.py)。

`models_sa.py` 定义 MindSpider 扩展表：

- `daily_news`
  - 每日热榜新闻。
  - 关键字段：`news_id/source_platform/title/url/crawl_date/rank_position/add_ts/last_modify_ts`。
  - 约束：`news_id` 唯一，`news_id + source_platform + crawl_date` 唯一。
- `daily_topics`
  - 每日话题分析。
  - 关键字段：`topic_id/topic_name/topic_description/keywords/extract_date/relevance_score/news_count/processing_status`。
  - `topic_id` 唯一，供其他表外键引用。
- `topic_news_relation`
  - 话题与新闻的关联表。
  - 外键：`topic_id -> daily_topics.topic_id`，`news_id -> daily_news.news_id`。
- `crawling_tasks`
  - 深度爬取任务表。
  - 关键字段：`task_id/topic_id/platform/search_keywords/task_status/start_time/end_time/total_crawled/success_count/error_count/scheduled_date`。
  - 外键：`topic_id -> daily_topics.topic_id`。

`models_bigdata.py` 定义 MediaCrawler 多平台内容表，典型模式是：

- 平台内容主表：`bilibili_video`、`douyin_aweme`、`kuaishou_video`、`weibo_note`、`xhs_note`、`tieba_note`、`zhihu_content`
- 平台评论表：`*_comment`
- 创作者/用户表：`*_creator`、`bilibili_up_info` 等
- 内容主表普遍包含：
  - 内容 ID：`video_id/aweme_id/note_id/content_id`
  - 作者：`user_id/nickname/avatar`
  - 文本：`title/desc/content/content_text`
  - 时间：`create_time/time/publish_time/created_time/create_date_time`
  - 互动：`liked_count/comment_count/share_count/view_count/...`
  - 来源：`source_keyword`
  - 关联：`topic_id -> daily_topics.topic_id`，`crawling_task_id -> crawling_tasks.task_id`

关系上，`daily_topics` 是中心：BroadTopicExtraction 生成它；DeepSentimentCrawling 使用它的关键词；平台内容表再通过 `topic_id` 和 `crawling_task_id` 回挂。

数据库初始化在 [MindSpider/schema/init_database.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/MindSpider/schema/init_database.py)：导入 `models_bigdata` 注册所有 ORM 类，然后 `Base.metadata.create_all` 一次性建表，并创建 `v_topic_crawling_stats`、`v_daily_summary` 视图。

**6. Flask + SocketIO 主应用编排**

顶层 Web 编排在 [app.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/app.py)。

它不是直接把四个 agent 都嵌进 Flask 请求里运行，而是采用“Flask 控制台 + 三个 Streamlit 子应用 + ReportEngine Blueprint + ForumEngine 监控”的架构：

- Flask 主站：`/` 渲染 [templates/index.html](/home/suuuu/develop/intelligence-system/archive/BettaFish/templates/index.html)。
- SocketIO：推送 `console_output`、`forum_message`、`status_update`。
- Streamlit 子应用：
  - Insight：`SingleEngineApp/insight_engine_streamlit_app.py`，端口 8501
  - Media：`SingleEngineApp/media_engine_streamlit_app.py`，端口 8502
  - Query：`SingleEngineApp/query_engine_streamlit_app.py`，端口 8503
- `initialize_system_components()` 做系统启动：
  - 初始化数据库。
  - 启动三个 Streamlit 子进程。
  - 启动 ForumEngine。
  - 初始化 ReportEngine。
- `/api/search` 会把查询 POST 到正在运行的 8501/8502/8503 子应用 `/api/search`。
- `/api/report/*` 由 `ReportEngine.flask_interface.report_bp` 注册，负责最终综合报告生成。
- `/api/system/start` 和 `/api/system/shutdown` 负责整套系统生命周期。
- `read_process_output()` 读取子进程 stdout，写到 `logs/{app}.log`，并通过 SocketIO 推送给前端。

这意味着主应用承担的是“进程编排、日志采集、前端实时状态、报告入口”，实际分析工作仍由各子引擎执行。

**7. ForumEngine 的作用**

ForumEngine 是三个分析引擎之间的“讨论层/主持层”，源码在 [ForumEngine/monitor.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/ForumEngine/monitor.py) 和 [ForumEngine/llm_host.py](/home/suuuu/develop/intelligence-system/archive/BettaFish/ForumEngine/llm_host.py)。

它的工作方式：

- 监控 `logs/insight.log`、`logs/media.log`、`logs/query.log`。
- 只捕获 SummaryNode 相关输出，目标模式包括 `FirstSummaryNode`、`ReflectionSummaryNode`、`nodes.summary_node`、`正在生成首次段落总结`、`正在生成反思总结`。
- 对 LLM 的 JSON 输出做解析，优先提取：
  - `paragraph_latest_state`
  - `updated_paragraph_latest_state`
- 写入统一论坛日志 `logs/forum.log`，格式类似：
  - `[时间] [INSIGHT] 内容`
  - `[时间] [MEDIA] 内容`
  - `[时间] [QUERY] 内容`
  - `[时间] [HOST] 内容`
- 每收集 5 条 agent 发言，`ForumHost.generate_host_speech()` 调用 LLM 生成主持人总结，写回 `forum.log`。
- `utils/forum_reader.py` 会被 InsightEngine 的 SummaryNode 读取，把最新 HOST 发言注入后续总结 prompt，形成轻量的跨 agent 反馈回路。
- ReportEngine 最终也会读取 forum logs，作为综合报告的补充上下文。

所以 ForumEngine 不是独立分析引擎，而是“观察三个引擎输出 → 结构化成论坛对话 → 主持人总结 → 反哺 prompt 与最终报告”的协同层。