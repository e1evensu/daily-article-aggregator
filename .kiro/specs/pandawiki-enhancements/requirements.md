# Requirements Document

## Introduction

本文档定义了 pandawiki-enhancements 功能增强的需求规格，包含四个核心模块：RAG 检索优化、Sitemap 导入器、统计分析系统和飞书双向机器人。这些增强功能旨在提升现有每日文章聚合器的检索质量、内容导入效率、数据分析能力和用户交互体验。

## Glossary

- **RAG_Engine**: 检索增强生成引擎，负责从知识库检索相关文档并生成回答
- **Knowledge_Base**: 知识库，使用 ChromaDB 存储文章向量和元数据
- **Similarity_Threshold**: 相似度阈值，用于过滤低相关性检索结果的分数界限
- **Chunk**: 文档分块，将长文档切分成的较小文本片段
- **Sitemap_Importer**: Sitemap 导入器，解析 sitemap.xml 并批量抓取页面内容
- **Crawl_Rule**: 抓取规则，定义页面抓取的包含/排除路径模式
- **Stats_System**: 统计分析系统，收集和分析文章阅读、问答等使用数据
- **Source_Quality**: 来源质量，评估数据源响应率和内容质量的指标
- **Feishu_Bot**: 飞书机器人，支持消息推送和交互式问答的飞书集成组件
- **Message_Thread**: 消息线程，飞书中将相关消息组织在一起的回复链
- **Event_Server**: 事件服务器，接收飞书回调事件的 HTTP 服务

## Requirements

### Requirement 1: RAG 相似度阈值控制

**User Story:** As a system administrator, I want to configure similarity threshold for RAG retrieval, so that I can filter out low-relevance results and improve answer quality.

#### Acceptance Criteria

1. THE RAG_Engine SHALL support configurable similarity_threshold parameter with default value 0.5
2. WHEN retrieving documents, THE RAG_Engine SHALL filter out results with similarity score below the configured threshold
3. WHEN similarity_threshold is set to 0, THE RAG_Engine SHALL return all retrieved results without filtering
4. WHEN similarity_threshold is set to 1, THE RAG_Engine SHALL only return exact matches
5. IF similarity_threshold is outside range [0, 1], THEN THE RAG_Engine SHALL raise a validation error with descriptive message

### Requirement 2: RAG 每文档最大分块数限制

**User Story:** As a system administrator, I want to limit the maximum chunks retrieved per document, so that I can prevent single documents from dominating search results.

#### Acceptance Criteria

1. THE RAG_Engine SHALL support configurable max_chunks_per_doc parameter with default value 3
2. WHEN retrieving documents, THE RAG_Engine SHALL return at most max_chunks_per_doc chunks from any single source document
3. WHEN max_chunks_per_doc is set to 0, THE RAG_Engine SHALL return unlimited chunks per document
4. THE RAG_Engine SHALL prioritize higher-scoring chunks when limiting per-document results
5. IF max_chunks_per_doc is negative, THEN THE RAG_Engine SHALL raise a validation error

### Requirement 3: RAG 历史对话上下文支持

**User Story:** As a user, I want the RAG system to consider my conversation history when retrieving documents, so that I can have more contextual and coherent multi-turn conversations.

#### Acceptance Criteria

1. WHEN processing a query, THE RAG_Engine SHALL accept optional conversation history as input
2. WHEN conversation history is provided, THE RAG_Engine SHALL use it to enhance query understanding and retrieval
3. THE RAG_Engine SHALL support configurable max_history_turns parameter with default value 5
4. WHEN conversation history exceeds max_history_turns, THE RAG_Engine SHALL use only the most recent turns
5. WHEN conversation history is empty or not provided, THE RAG_Engine SHALL process the query without historical context

### Requirement 4: RAG 检索结果去重和排序优化

**User Story:** As a user, I want deduplicated and well-sorted retrieval results, so that I can get diverse and relevant information without redundancy.

#### Acceptance Criteria

1. THE RAG_Engine SHALL deduplicate retrieved chunks based on content similarity
2. WHEN two chunks have content similarity above 0.95, THE RAG_Engine SHALL keep only the higher-scoring chunk
3. THE RAG_Engine SHALL sort final results by relevance score in descending order
4. THE RAG_Engine SHALL support secondary sorting by source diversity when scores are equal
5. THE RAG_Engine SHALL return deduplicated results count in response metadata

### Requirement 5: Sitemap XML 解析

**User Story:** As a content manager, I want to parse sitemap.xml files to discover pages, so that I can batch import content from websites.

#### Acceptance Criteria

1. WHEN a valid sitemap.xml URL is provided, THE Sitemap_Importer SHALL parse and extract all page URLs
2. THE Sitemap_Importer SHALL support standard sitemap format with loc, lastmod, changefreq, and priority elements
3. THE Sitemap_Importer SHALL support sitemap index files containing references to multiple sitemaps
4. IF sitemap.xml is malformed, THEN THE Sitemap_Importer SHALL return a descriptive parsing error
5. THE Sitemap_Importer SHALL handle gzip-compressed sitemaps transparently

### Requirement 6: Sitemap 增量更新

**User Story:** As a content manager, I want to only crawl new or updated pages, so that I can save time and resources during content synchronization.

#### Acceptance Criteria

1. THE Sitemap_Importer SHALL track last crawl timestamp for each URL
2. WHEN lastmod is available, THE Sitemap_Importer SHALL skip pages not modified since last crawl
3. WHEN lastmod is not available, THE Sitemap_Importer SHALL use content hash comparison for change detection
4. THE Sitemap_Importer SHALL support force_refresh option to bypass incremental logic
5. THE Sitemap_Importer SHALL report statistics including new_pages, updated_pages, and skipped_pages counts

### Requirement 7: HTML 转 Markdown 自动转换

**User Story:** As a content manager, I want HTML content automatically converted to Markdown, so that I can store clean, structured text in the knowledge base.

#### Acceptance Criteria

1. WHEN importing HTML content, THE Sitemap_Importer SHALL convert it to Markdown format
2. THE Sitemap_Importer SHALL preserve document structure including headings, lists, tables, and code blocks
3. THE Sitemap_Importer SHALL extract and preserve hyperlinks with their URLs
4. THE Sitemap_Importer SHALL remove script, style, and navigation elements from conversion
5. THE Sitemap_Importer SHALL handle malformed HTML gracefully without crashing
6. FOR ALL valid HTML documents, converting to Markdown then parsing the Markdown SHALL preserve the semantic structure (round-trip property)

### Requirement 8: 配置化抓取规则

**User Story:** As a content manager, I want to configure include/exclude path patterns, so that I can control which pages are imported from a sitemap.

#### Acceptance Criteria

1. THE Sitemap_Importer SHALL support include_patterns configuration as list of glob patterns
2. THE Sitemap_Importer SHALL support exclude_patterns configuration as list of glob patterns
3. WHEN both include and exclude patterns match a URL, THE Sitemap_Importer SHALL apply exclude pattern (exclude takes precedence)
4. WHEN no include_patterns are configured, THE Sitemap_Importer SHALL include all URLs by default
5. THE Sitemap_Importer SHALL support regex patterns in addition to glob patterns
6. IF a pattern is invalid, THEN THE Sitemap_Importer SHALL raise a configuration error with pattern details

### Requirement 9: 文章阅读统计

**User Story:** As a system administrator, I want to track article reading statistics, so that I can understand content popularity and user engagement.

#### Acceptance Criteria

1. THE Stats_System SHALL record page view events with article_id, timestamp, and user_id (if available)
2. THE Stats_System SHALL aggregate daily, weekly, and monthly view counts per article
3. THE Stats_System SHALL provide hot_articles API returning top N articles by view count
4. THE Stats_System SHALL support time range filtering for statistics queries
5. THE Stats_System SHALL deduplicate views from same user within configurable time window (default 5 minutes)

### Requirement 10: 问答统计

**User Story:** As a system administrator, I want to track Q&A usage statistics, so that I can monitor system utilization and identify popular topics.

#### Acceptance Criteria

1. THE Stats_System SHALL record each Q&A interaction with query, response_time, and confidence_score
2. THE Stats_System SHALL aggregate total queries, average response time, and average confidence by time period
3. THE Stats_System SHALL track query success rate (queries with confidence above threshold)
4. THE Stats_System SHALL provide hot_queries API returning frequently asked questions
5. THE Stats_System SHALL support filtering statistics by user_id and chat_id

### Requirement 11: 来源质量评估

**User Story:** As a system administrator, I want to evaluate data source quality, so that I can identify and prioritize reliable sources.

#### Acceptance Criteria

1. THE Stats_System SHALL track response_rate for each data source (successful fetches / total attempts)
2. THE Stats_System SHALL track average content_length and content_quality_score per source
3. THE Stats_System SHALL calculate source_reliability_score combining response_rate and content_quality
4. THE Stats_System SHALL provide source_ranking API returning sources sorted by reliability
5. WHEN source_reliability_score falls below threshold, THE Stats_System SHALL flag the source for review

### Requirement 12: 热门话题追踪

**User Story:** As a system administrator, I want to track trending topics, so that I can understand user interests and content gaps.

#### Acceptance Criteria

1. THE Stats_System SHALL extract keywords from user queries using NLP techniques
2. THE Stats_System SHALL aggregate keyword frequency over configurable time windows
3. THE Stats_System SHALL provide trending_topics API returning top keywords with trend direction
4. THE Stats_System SHALL detect topic spikes by comparing current frequency to historical baseline
5. THE Stats_System SHALL support topic categorization using predefined taxonomy

### Requirement 13: 数据可视化报表

**User Story:** As a system administrator, I want visual reports of system statistics, so that I can quickly understand system health and usage patterns.

#### Acceptance Criteria

1. THE Stats_System SHALL provide JSON API endpoints for all statistics suitable for charting
2. THE Stats_System SHALL support time-series data format for trend visualization
3. THE Stats_System SHALL provide summary dashboard data including key metrics
4. THE Stats_System SHALL support data export in CSV format for external analysis
5. THE Stats_System SHALL cache computed statistics with configurable TTL for performance

### Requirement 14: 飞书群内提问支持

**User Story:** As a user, I want to ask questions directly in Feishu group chat, so that I can get answers without leaving my workflow.

#### Acceptance Criteria

1. WHEN a user sends a message in a group where the bot is present, THE Feishu_Bot SHALL receive the message event
2. THE Feishu_Bot SHALL integrate with existing QA_Engine to process questions
3. THE Feishu_Bot SHALL respond with answers in the same group chat
4. THE Feishu_Bot SHALL include source links in responses when available
5. IF QA_Engine returns low confidence answer, THEN THE Feishu_Bot SHALL indicate uncertainty in response

### Requirement 15: @ 机器人触发

**User Story:** As a user, I want to trigger the bot by @mentioning it, so that I can control when the bot responds and avoid noise.

#### Acceptance Criteria

1. WHEN a message contains @bot_mention, THE Feishu_Bot SHALL process the message as a question
2. WHEN a message does not contain @bot_mention, THE Feishu_Bot SHALL ignore the message by default
3. THE Feishu_Bot SHALL support configurable always_respond mode for dedicated Q&A groups
4. THE Feishu_Bot SHALL extract the actual question by removing the @mention from message text
5. THE Feishu_Bot SHALL handle multiple @mentions in single message gracefully

### Requirement 16: 回复消息线程化

**User Story:** As a user, I want bot responses in message threads, so that conversations stay organized and don't clutter the main chat.

#### Acceptance Criteria

1. WHEN responding to a question, THE Feishu_Bot SHALL reply in a thread attached to the original message
2. WHEN a follow-up question is asked in the same thread, THE Feishu_Bot SHALL maintain conversation context
3. THE Feishu_Bot SHALL support configurable thread_replies option (enabled by default)
4. WHEN thread_replies is disabled, THE Feishu_Bot SHALL reply directly in the main chat
5. THE Feishu_Bot SHALL include original question reference in thread replies for clarity

### Requirement 17: 飞书事件服务器增强

**User Story:** As a system administrator, I want a robust event server for Feishu callbacks, so that the bot can reliably receive and process messages.

#### Acceptance Criteria

1. THE Event_Server SHALL handle Feishu URL verification challenge requests
2. THE Event_Server SHALL validate request signatures using configured encrypt_key
3. THE Event_Server SHALL process message events asynchronously to avoid timeout
4. IF event processing fails, THEN THE Event_Server SHALL log error and return success to prevent retries
5. THE Event_Server SHALL implement idempotency to handle duplicate event deliveries
6. THE Event_Server SHALL support health check endpoint for monitoring

