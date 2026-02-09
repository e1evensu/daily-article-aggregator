# Implementation Plan: PandaWiki Enhancements

## Overview

本实现计划将四个功能模块分解为可执行的编码任务。每个任务都是增量式的，构建在前一个任务的基础上。任务按模块组织，每个模块内部按依赖顺序排列。

## Tasks

- [x] 1. Module 1: RAG 检索优化
  - [x] 1.1 创建 RAG 增强配置类
    - 在 `src/qa/config.py` 中添加 `RetrievalConfig` 数据类
    - 实现 `similarity_threshold`, `max_chunks_per_doc`, `max_history_turns`, `dedup_threshold` 参数
    - 实现 `validate()` 方法进行参数校验
    - 更新 `config.yaml` 添加 `rag_enhancement` 配置节
    - _Requirements: 1.1, 1.5, 2.1, 2.5, 3.3_

  - [ ]* 1.2 编写配置验证属性测试
    - **Property 2: Invalid Threshold Rejection**
    - **Property 4: Invalid Max Chunks Rejection**
    - **Validates: Requirements 1.5, 2.5**

  - [x] 1.3 实现相似度阈值过滤
    - 在 `src/qa/` 目录创建 `enhanced_retriever.py`
    - 实现 `EnhancedRetriever` 类
    - 实现 `_filter_by_threshold()` 方法
    - 集成到现有 `KnowledgeBase.search()` 流程
    - _Requirements: 1.2, 1.3, 1.4_

  - [ ]* 1.4 编写阈值过滤属性测试
    - **Property 1: Similarity Threshold Filtering**
    - **Validates: Requirements 1.2, 1.3, 1.4**

  - [x] 1.5 实现每文档分块数限制
    - 在 `EnhancedRetriever` 中实现 `_limit_per_document()` 方法
    - 按文档 ID 分组，保留最高分的 N 个分块
    - _Requirements: 2.2, 2.3, 2.4_

  - [ ]* 1.6 编写分块限制属性测试
    - **Property 3: Per-Document Chunk Limiting**
    - **Validates: Requirements 2.2, 2.4**

  - [x] 1.7 实现历史对话上下文支持
    - 创建 `HistoryAwareQueryBuilder` 类
    - 实现 `build_query()` 方法，将历史对话融入查询
    - 实现历史轮数截断逻辑
    - 集成到 `QAEngine.process_query()`
    - _Requirements: 3.1, 3.2, 3.4, 3.5_

  - [ ]* 1.8 编写历史截断属性测试
    - **Property 5: History Truncation**
    - **Validates: Requirements 3.4**

  - [x] 1.9 实现检索结果去重
    - 在 `EnhancedRetriever` 中实现 `_deduplicate()` 方法
    - 使用内容相似度计算（复用 embedding 服务）
    - 保留高分块，移除相似低分块
    - _Requirements: 4.1, 4.2_

  - [ ]* 1.10 编写去重属性测试
    - **Property 6: Content Deduplication**
    - **Validates: Requirements 4.1, 4.2**

  - [x] 1.11 实现结果排序优化
    - 在 `EnhancedRetriever` 中实现 `_sort_results()` 方法
    - 主排序：相关性分数降序
    - 次排序：来源多样性
    - 返回去重计数元数据
    - _Requirements: 4.3, 4.4, 4.5_

  - [ ]* 1.12 编写排序属性测试
    - **Property 7: Result Ordering**
    - **Validates: Requirements 4.3**

- [x] 2. Checkpoint - RAG 模块完成
  - 确保所有 RAG 相关测试通过
  - 如有问题请询问用户

- [ ] 3. Module 2: Sitemap 导入器
  - [x] 3.1 创建 Sitemap 解析器
    - 在 `src/fetchers/` 目录创建 `sitemap_importer.py`
    - 实现 `SitemapEntry` 数据类
    - 实现 `SitemapParser` 类
    - 支持标准 sitemap 和 sitemap index 格式
    - 支持 gzip 压缩处理
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

  - [ ]* 3.2 编写 Sitemap 解析属性测试
    - **Property 8: Sitemap Parsing Completeness**
    - **Property 9: Malformed Sitemap Error Handling**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

  - [x] 3.3 实现抓取规则引擎
    - 创建 `CrawlRules` 数据类
    - 实现 `CrawlRuleEngine` 类
    - 支持 glob 和 regex 模式
    - 实现 include/exclude 优先级逻辑
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 3.4 编写抓取规则属性测试
    - **Property 14: Crawl Rule Matching**
    - **Property 15: Invalid Pattern Error**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6**

  - [x] 3.5 实现增量爬虫
    - 创建 `CrawlState` 和 `CrawlStats` 数据类
    - 实现 `CrawlStateStore` 用于持久化爬取状态
    - 实现 `IncrementalCrawler` 类
    - 支持 lastmod 和 content hash 变更检测
    - 支持 force_refresh 选项
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 3.6 编写增量爬取属性测试
    - **Property 10: Incremental Crawl Logic**
    - **Property 11: Crawl Statistics Consistency**
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5**

  - [x] 3.7 实现 HTML 转 Markdown 转换器
    - 创建 `HTMLToMarkdownConverter` 类
    - 使用 BeautifulSoup 解析 HTML
    - 使用 markdownify 或自定义逻辑转换
    - 保留标题、列表、表格、代码块、链接
    - 移除 script, style, nav, footer, header
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 3.8 编写 HTML 转换属性测试
    - **Property 12: HTML to Markdown Conversion**
    - **Property 13: HTML-Markdown Round Trip**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6**

  - [x] 3.9 集成 Sitemap 导入器到知识库
    - 创建 `SitemapImporter` 主类整合所有组件
    - 实现 `import_from_sitemap()` 方法
    - 集成到 `KnowledgeBase.add_articles()` 流程
    - 更新 `config.yaml` 添加 `sitemap_importer` 配置节
    - _Requirements: 5.1, 6.1, 7.1, 8.1_

- [x] 4. Checkpoint - Sitemap 模块完成
  - 确保所有 Sitemap 相关测试通过
  - 如有问题请询问用户

- [ ] 5. Module 3: 统计分析系统
  - [x] 5.1 创建统计数据模型和存储
    - 在 `src/` 目录创建 `stats/` 子目录
    - 创建 `models.py` 定义 `PageViewEvent`, `QAEvent`, `SourceQuality` 等数据类
    - 创建 `store.py` 实现 `StatsStore` 类（SQLite 后端）
    - 创建数据库 schema 和迁移脚本
    - _Requirements: 9.1, 10.1, 11.1_

  - [x] 5.2 实现统计收集器
    - 创建 `collector.py` 实现 `StatsCollector` 类
    - 实现 `record_page_view()` 方法（含去重逻辑）
    - 实现 `record_qa_event()` 方法
    - 实现 `record_source_fetch()` 方法
    - _Requirements: 9.1, 9.5, 10.1, 11.1_

  - [ ]* 5.3 编写页面浏览统计属性测试
    - **Property 16: Page View Recording and Deduplication**
    - **Property 17: View Count Aggregation**
    - **Validates: Requirements 9.1, 9.2, 9.5**

  - [x] 5.4 实现统计聚合器
    - 创建 `aggregator.py` 实现 `StatsAggregator` 类
    - 实现 `get_hot_articles()` 方法
    - 实现 `get_qa_stats()` 方法
    - 实现 `get_source_ranking()` 方法
    - 实现时间范围过滤
    - _Requirements: 9.2, 9.3, 9.4, 10.2, 10.3, 10.4, 10.5, 11.4_

  - [ ]* 5.5 编写统计聚合属性测试
    - **Property 18: Hot Articles Ranking**
    - **Property 19: QA Statistics Accuracy**
    - **Property 20: Hot Queries Ranking**
    - **Validates: Requirements 9.3, 9.4, 10.2, 10.3, 10.4**

  - [x] 5.6 实现来源质量评估
    - 在 `StatsAggregator` 中实现来源质量计算
    - 实现 `response_rate`, `avg_content_length`, `reliability_score` 计算
    - 实现低质量来源标记逻辑
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 5.7 编写来源质量属性测试
    - **Property 21: Source Quality Metrics**
    - **Property 22: Source Ranking**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5**

  - [x] 5.8 实现话题追踪器
    - 创建 `topic_tracker.py` 实现 `TopicTracker` 类
    - 实现关键词提取（使用 jieba 或简单规则）
    - 实现频率聚合和趋势计算
    - 实现话题突增检测
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ]* 5.9 编写话题追踪属性测试
    - **Property 23: Topic Frequency Aggregation**
    - **Property 24: Topic Spike Detection**
    - **Validates: Requirements 12.2, 12.4**

  - [x] 5.10 实现统计 API 和数据导出
    - 创建 `api.py` 实现 JSON API 端点
    - 实现时间序列数据格式
    - 实现 CSV 导出功能
    - 实现统计缓存（带 TTL）
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

  - [ ]* 5.11 编写 API 和导出属性测试
    - **Property 25: CSV Export Validity**
    - **Property 26: Statistics Cache Behavior**
    - **Validates: Requirements 13.4, 13.5**

  - [x] 5.12 集成统计系统到主流程
    - 在 `QAEngine` 中集成 QA 事件记录
    - 在各 fetcher 中集成来源抓取记录
    - 更新 `config.yaml` 添加 `stats_system` 配置节
    - _Requirements: 9.1, 10.1, 11.1_

- [x] 6. Checkpoint - 统计模块完成
  - 确保所有统计相关测试通过
  - 如有问题请询问用户

- [ ] 7. Module 4: 飞书双向机器人
  - [x] 7.1 增强飞书事件服务器
    - 更新 `src/qa/event_server.py` 为 `EnhancedEventServer`
    - 实现 URL 验证挑战处理
    - 实现请求签名验证
    - 实现事件幂等性处理（去重）
    - 添加健康检查端点
    - _Requirements: 17.1, 17.2, 17.4, 17.5, 17.6_

  - [ ]* 7.2 编写事件服务器属性测试
    - **Property 33: URL Verification Challenge**
    - **Property 34: Request Signature Validation**
    - **Property 35: Event Processing Idempotency**
    - **Property 36: Error Handling Response**
    - **Validates: Requirements 17.1, 17.2, 17.4, 17.5**

  - [x] 7.3 实现飞书事件处理器
    - 创建 `src/bots/feishu_event_handler.py`
    - 实现 `FeishuMessage` 数据类
    - 实现 `FeishuEventHandler` 类
    - 实现 @mention 检测和提取逻辑
    - 实现 always_respond 模式
    - _Requirements: 14.1, 14.2, 15.1, 15.2, 15.3, 15.4, 15.5_

  - [ ]* 7.4 编写消息处理属性测试
    - **Property 27: Mention-Based Trigger**
    - **Property 28: Mention Extraction**
    - **Validates: Requirements 15.1, 15.2, 15.3, 15.4**

  - [x] 7.5 实现线程回复器
    - 创建 `ThreadReplier` 类
    - 实现线程回复 API 调用
    - 实现回复内容构建（含来源链接）
    - 实现低置信度提示
    - 支持 thread_replies 配置开关
    - _Requirements: 14.3, 14.4, 14.5, 16.1, 16.2, 16.3, 16.4, 16.5_

  - [ ]* 7.6 编写线程回复属性测试
    - **Property 29: Source Link Inclusion**
    - **Property 30: Low Confidence Indication**
    - **Property 31: Thread Reply Behavior**
    - **Property 32: Thread Reply Content**
    - **Validates: Requirements 14.4, 14.5, 16.1, 16.2, 16.4, 16.5**

  - [x] 7.7 集成飞书双向机器人
    - 更新 `FeishuBot` 类支持双向交互
    - 集成 `FeishuEventHandler` 和 `ThreadReplier`
    - 集成 `QAEngine` 进行问答处理
    - 更新 `config.yaml` 添加 `feishu_interactive` 配置节
    - _Requirements: 14.2, 14.3, 16.1_

- [x] 8. Checkpoint - 飞书模块完成
  - 确保所有飞书相关测试通过
  - 如有问题请询问用户

- [ ] 9. 最终集成和文档
  - [x] 9.1 更新主配置文件
    - 整合所有新配置节到 `config.yaml`
    - 添加配置示例和注释
    - 验证配置加载逻辑
    - _Requirements: All_

  - [x] 9.2 更新 README 文档
    - 添加新功能说明
    - 添加配置指南
    - 添加使用示例
    - _Requirements: All_

- [x] 10. Final Checkpoint - 全部完成
  - 确保所有测试通过
  - 如有问题请询问用户

## Notes

- 标记 `*` 的任务为可选测试任务，可跳过以加快 MVP 开发
- 每个任务都引用了具体的需求编号以便追溯
- Checkpoint 任务用于阶段性验证，确保增量进展
- 属性测试使用 Hypothesis 框架，每个测试至少运行 100 次迭代
