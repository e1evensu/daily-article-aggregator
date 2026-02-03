# 每日文章聚合器

技术内容聚合系统，多源数据抓取 + AI 分析 + 飞书推送。

## 功能清单

### 1. 数据源 (8+)

| 数据源 | 说明 | 配置项 |
|--------|------|--------|
| arXiv | 论文，支持分类过滤 (cs.AI/cs.CR等)，关键词过滤 | `sources.arxiv` |
| RSS | OPML 批量导入，并发抓取，支持代理 | `sources.rss` |
| DBLP | 安全四大顶会 (S&P/CCS/USENIX/NDSS) | `data_sources.dblp` |
| NVD | CVE 漏洞库，支持 API Key 提速 | `data_sources.nvd` |
| KEV | CISA 在野利用漏洞 | `data_sources.kev` |
| HuggingFace | 每日热门论文 | `data_sources.huggingface` |
| Papers With Code | 带代码的论文 | `data_sources.pwc` |
| 大厂博客 | OpenAI/DeepMind/Anthropic | `data_sources.blogs` |

### 2. AI 分析

| 功能 | 说明 | 配置项 |
|------|------|--------|
| 摘要生成 | 200字精准摘要 | `ai.enabled` |
| 中文翻译 | 英文摘要翻译，保留专业术语 | `ai.translate` |
| 分类标签 | AI/安全/系统/编程语言/... | 自动 |
| 漏洞评估 | AI 判断漏洞实际危害 | `vulnerability_filter.enable_ai_assessment` |
| 优先级评分 | 0-100 分，考虑来源/内容/时效 | `priority_scoring.enabled` |
| 关键词提取 | AI 提取核心关键词 | 自动 |

### 3. 漏洞过滤 (三层)

| 层级 | 方法 | 配置项 |
|------|------|--------|
| 规则过滤 | CVSS >= 7.0，影响主流产品 | 内置 |
| 数据过滤 | GitHub Star > 阈值，IP 资产量 > 阈值 | `vulnerability_filter.github_star_threshold` |
| AI 过滤 | 评估利用难度、实际危害 | `vulnerability_filter.enable_ai_assessment` |

### 4. 话题聚合

| 功能 | 说明 | 配置项 |
|------|------|--------|
| AI Embedding | 使用 text-embedding 计算语义相似度 | `topic_aggregation.use_ai_similarity` |
| jieba 备选 | AI 不可用时用 jieba 分词 | 自动降级 |
| Union-Find 聚类 | 相似度 >= 阈值的文章聚合 | `topic_aggregation.similarity_threshold` |
| 时间窗口 | 只聚合 N 天内的文章 | `topic_aggregation.time_window_days` |
| 聚合阈值 | 达到 N 篇才生成综述 | `topic_aggregation.aggregation_threshold` |
| 综述生成 | AI 生成结构化综述 (背景/观点/影响/总结) | 自动 |
| 质量过滤 | 黑名单域名过滤 (CSDN/知乎/简书) | `topic_aggregation.blacklist_domains` |
| 可信来源 | 白名单来源优先 | `topic_aggregation.trusted_sources` |

### 5. 分级推送

| 级别 | 内容 | 配置项 |
|------|------|--------|
| Level 1 (前10%) | 完整摘要 + 关键词 + 链接 | `tiered_push.level1_threshold` |
| Level 2 (10%-40%) | 标题 + 简要摘要 | `tiered_push.level2_threshold` |
| Level 3 (40%-100%) | 仅标题列表 | 剩余 |

### 6. 输出

| 输出 | 说明 | 配置项 |
|------|------|--------|
| 飞书机器人 | Webhook 推送到群聊 | `feishu.webhook_url` |
| 飞书多维表格 | 数据可视化管理 | `feishu_bitable.*` |
| 飞书文档 | 综述发布 | `topic_aggregation` |
| 知识 RSS | 综述生成 RSS 2.0 订阅源 | `topic_aggregation` |
| SQLite | 本地数据库存储 | `database.path` |

### 7. 去重

| 方法 | 说明 |
|------|------|
| URL 去重 | 完全相同的 URL 跳过 |
| 标题相似度 | 标题相似的文章跳过 |

### 8. 断点续传

| 功能 | 说明 | 配置项 |
|------|------|--------|
| 抓取检查点 | 保存已完成的订阅源和文章 | `checkpoint.enabled` |
| 处理检查点 | 保存已处理的文章 | `checkpoint.enabled` |
| 自动保存 | 每 N 条自动保存 | `checkpoint.save_interval` |
| 过期清理 | N 小时后自动清理 | `checkpoint.max_age_hours` |
| 命令行 | `--checkpoint-status` / `--clear-checkpoint` | - |

### 9. 调度

| 功能 | 说明 | 配置项 |
|------|------|--------|
| 定时执行 | 每天指定时间自动运行 | `schedule.time` |
| 手动执行 | `--once` 参数 | - |
| 时区 | 支持配置时区 | `schedule.timezone` |

### 10. 知识库问答机器人

| 功能 | 说明 | 配置项 |
|------|------|--------|
| 向量知识库 | ChromaDB 存储文章向量 | `knowledge_qa.knowledge_base` |
| 语义搜索 | 基于 Embedding 的相似度检索 | `knowledge_qa.knowledge_base.n_results` |
| RAG 问答 | 检索增强生成回答 | `knowledge_qa.qa_engine` |
| 飞书集成 | 支持群聊 @机器人 和私聊 | `knowledge_qa.event_server` |
| 上下文记忆 | 多轮对话上下文保持 | `knowledge_qa.context_manager` |
| 频率限制 | 用户级/全局级限流 | `knowledge_qa.rate_limiter` |
| 来源归属 | 回答附带文章来源链接 | 自动 |

### 11. 工具脚本

| 脚本 | 功能 |
|------|------|
| `scripts/run_topic_aggregation.py` | 独立运行话题聚合 |
| `scripts/evaluate_feeds.py` | 评估 RSS 源质量 (活跃度/原创性/技术深度) |
| `scripts/merge_opml.py` | 多个 OPML 文件去重合并 |
| `scripts/setup_bitable.py` | 初始化飞书多维表格 |
| `scripts/init_knowledge_base.py` | 初始化/重建知识库 |
| `scripts/sync_knowledge_base.py` | 增量同步知识库 |
| `scripts/run_qa_server.py` | 启动问答服务器 |

## 运行

```bash
# 安装
pip install -r requirements.txt
cp .env.example .env

# 单次执行
python main.py --once

# 定时调度
python main.py

# 断点状态
python main.py --checkpoint-status

# 清除断点
python main.py --clear-checkpoint

# 话题聚合
python scripts/run_topic_aggregation.py --days 7 --stats

# 知识库问答
python scripts/init_knowledge_base.py --rebuild  # 初始化知识库
python scripts/sync_knowledge_base.py --hours 24  # 增量同步
python scripts/run_qa_server.py --port 8080       # 启动问答服务器
```

## 服务器部署

```bash
tmux new -s daily
python3.11 main.py
# Ctrl+B D 退出
```

## 配置

### 环境变量 (.env)

```
OPENAI_API_KEY=
OPENAI_API_BASE=
OPENAI_MODEL=gpt-4o-mini
FEISHU_WEBHOOK_URL=
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_BITABLE_APP_TOKEN=
FEISHU_BITABLE_TABLE_ID=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
GITHUB_TOKEN=
NVD_API_KEY=
```

### config.yaml 完整配置

```yaml
# 数据源
sources:
  arxiv:
    enabled: true
    categories: [cs.AI, cs.CL, cs.CR]
    keywords: [security, safety, llm]
    max_results: 100
  rss:
    enabled: true
    opml_path: "feeds.opml"

# AI
ai:
  enabled: true
  api_base: "${OPENAI_API_BASE}"
  api_key: "${OPENAI_API_KEY}"
  model: "${OPENAI_MODEL:gpt-4o-mini}"
  translate: true

# 飞书
feishu:
  webhook_url: "${FEISHU_WEBHOOK_URL}"

feishu_bitable:
  enabled: true
  app_id: "${FEISHU_APP_ID}"
  app_secret: "${FEISHU_APP_SECRET}"

# 调度
schedule:
  time: "07:00"
  timezone: "Asia/Shanghai"

# 断点续传
checkpoint:
  enabled: true
  dir: "data/checkpoints"
  max_age_hours: 24
  save_interval: 10

# 新数据源
data_sources:
  dblp:
    enabled: true
    conferences: [sp, ccs, uss, ndss]
  nvd:
    enabled: true
    days_back: 7
  kev:
    enabled: true
    days_back: 30
  huggingface:
    enabled: true
  pwc:
    enabled: true
    limit: 50
  blogs:
    enabled: true
    sources: [openai, deepmind, anthropic]

# 漏洞过滤
vulnerability_filter:
  enabled: true
  github_star_threshold: 1000
  ip_asset_threshold: 300
  enable_ai_assessment: true

# 分级推送
tiered_push:
  enabled: true
  level1_threshold: 0.10
  level2_threshold: 0.40

# 优先级评分
priority_scoring:
  enabled: true
  source_weights:
    kev: 1.5
    nvd: 1.2
    dblp: 1.3
    huggingface: 1.1
    pwc: 1.1
    blog: 1.0
    arxiv: 1.0
    rss: 0.8

# 话题聚合
topic_aggregation:
  enabled: true
  similarity_threshold: 0.7
  aggregation_threshold: 3
  time_window_days: 7
  use_ai_similarity: true
  embedding_model: "text-embedding-3-small"
  blacklist_domains:
    - csdn.net
    - zhihu.com
    - jianshu.com
    - blog.51cto.com
  trusted_sources:
    - arxiv.org
    - github.com
    - openai.com

# 知识库问答
knowledge_qa:
  event_server:
    host: "0.0.0.0"
    port: 8080
    verification_token: "${FEISHU_VERIFICATION_TOKEN}"
    encrypt_key: "${FEISHU_ENCRYPT_KEY:}"
  knowledge_base:
    persist_directory: "data/chroma"
    collection_name: "articles"
    chunk_size: 500
    chunk_overlap: 50
    n_results: 5
  context_manager:
    max_history: 10
    ttl_minutes: 30
  rate_limiter:
    max_requests_per_minute: 10
    global_max_requests_per_minute: 100
  qa_engine:
    max_answer_length: 500
    min_confidence: 0.3
```

## 项目结构

```
src/
├── fetchers/              # 数据获取
│   ├── arxiv_fetcher.py
│   ├── rss_fetcher.py
│   ├── dblp_fetcher.py
│   ├── nvd_fetcher.py
│   ├── kev_fetcher.py
│   ├── huggingface_fetcher.py
│   ├── pwc_fetcher.py
│   └── blog_fetcher.py
├── analyzers/
│   └── ai_analyzer.py     # AI 摘要/分类/翻译/漏洞评估/优先级评分
├── filters/
│   └── vulnerability_filter.py  # 漏洞三层过滤
├── scoring/
│   └── priority_scorer.py       # 优先级评分
├── pushers/
│   └── tiered_pusher.py         # 分级推送
├── bots/
│   ├── feishu_bot.py            # 飞书机器人
│   └── feishu_bitable.py        # 飞书多维表格
├── aggregation/                  # 话题聚合
│   ├── aggregation_engine.py    # AI Embedding 聚类
│   ├── synthesis_generator.py   # 综述生成
│   ├── quality_filter.py        # 质量过滤 (黑名单/白名单)
│   ├── feishu_doc_publisher.py  # 飞书文档发布
│   ├── knowledge_rss_generator.py # RSS 生成
│   ├── topic_aggregation_system.py # 系统主类
│   └── models.py                # 数据模型
├── qa/                           # 知识库问答
│   ├── embedding_service.py     # 文本向量化
│   ├── knowledge_base.py        # ChromaDB 知识库
│   ├── context_manager.py       # 对话上下文
│   ├── query_processor.py       # 查询解析
│   ├── qa_engine.py             # RAG 问答引擎
│   ├── rate_limiter.py          # 频率限制
│   ├── event_server.py          # 飞书事件服务器
│   ├── config.py                # QA 配置
│   └── models.py                # QA 数据模型
├── evaluators/
│   └── rss_evaluator.py         # RSS 源质量评估
├── processors/
│   └── content_processor.py     # 内容处理
├── utils/
│   ├── checkpoint.py            # 断点续传
│   └── deduplication.py         # 去重
├── repository.py                # SQLite 数据库
├── scheduler.py                 # 定时调度
├── config.py                    # 配置加载
└── models.py                    # 通用数据模型

scripts/
├── run_topic_aggregation.py     # 话题聚合脚本
├── evaluate_feeds.py            # RSS 评估脚本
├── merge_opml.py                # OPML 合并脚本
├── setup_bitable.py             # 多维表格初始化
├── init_knowledge_base.py       # 知识库初始化
├── sync_knowledge_base.py       # 知识库增量同步
└── run_qa_server.py             # 问答服务器启动
```

## 测试

```bash
pytest tests/ -v
```
