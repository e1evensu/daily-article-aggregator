# 📊 Daily Article Aggregator - 项目状态文档

> 最后更新: 2026-02-09

本文档详细记录项目的所有模块、功能状态、实现方式和后续计划。

---

## 🎯 项目核心目标

1. **爬取文章** - 从多种数据源自动抓取技术文章
2. **飞书交互** - 通过飞书进行推送、问答、反馈
3. **自动优化系统** - 根据用户反馈自动优化推荐

**注意**: 本项目不包含 Web 系统，所有交互基于飞书。

---

## 📁 模块总览

| 模块 | 状态 | 说明 |
|------|------|------|
| 数据抓取 (Fetchers) | ✅ 完成 | 13种数据源 |
| AI分析 (Analyzers) | ✅ 完成 | 文章摘要、分类、翻译 |
| 内容处理 (Processors) | ✅ 完成 | HTML转Markdown |
| 优先级评分 (Scoring) | ✅ 完成 | 多维度评分 |
| 智能筛选 (Pushers) | ✅ 完成 | 智能选择推送文章 |
| 飞书推送 (Bots) | ✅ 完成 | Webhook + 多维表格 |
| 知识库问答 (QA) | ✅ 完成 | ChromaDB + RAG |
| 用户反馈 (Feedback) | ✅ 完成 | 偏好学习 |
| RSS评估 (Evaluators) | ✅ 完成 | 源质量评估 |
| 统计分析 (Stats) | ✅ 完成 | 数据统计 |
| 话题聚合 (Aggregation) | ✅ 完成 | 相似文章聚合 |
| 调度器 (Scheduler) | ✅ 完成 | 定时任务 |
| 断点续传 (Checkpoint) | ✅ 完成 | 任务恢复 |

---

## 📥 数据抓取模块 (src/fetchers/)

### 已实现的数据源 (13种)

| 数据源 | 文件 | 状态 | 说明 |
|--------|------|------|------|
| RSS/Atom | `rss_fetcher.py` | ✅ | 标准RSS订阅 |
| arXiv | `arxiv_fetcher.py` | ✅ | 学术论文 |
| DBLP | `dblp_fetcher.py` | ✅ | 安全四大顶会 (S&P, CCS, USENIX, NDSS) |
| NVD | `nvd_fetcher.py` | ✅ | 漏洞数据库 (CVSS≥7.0) |
| KEV | `kev_fetcher.py` | ✅ | CISA在野利用漏洞 |
| HuggingFace | `huggingface_fetcher.py` | ✅ | AI论文 |
| Papers With Code | `pwc_fetcher.py` | ✅ | 带代码的论文 |
| GitHub | `github_fetcher.py` | ✅ | 热门项目 |
| 大厂博客 | `blog_fetcher.py` | ✅ | OpenAI/DeepMind/Anthropic |
| 腾讯混元 | `web_blog_fetcher.py` | ✅ | 混元研究博客 |
| Anthropic Red | `web_blog_fetcher.py` | ✅ | Anthropic红队博客 |
| Atum Blog | `web_blog_fetcher.py` | ✅ | atum.li技术博客 |
| Sitemap | `sitemap_importer.py` | ✅ | 通用Sitemap导入 |

### 配置方式

在 `config.yaml` 的 `data_sources` 部分配置：

```yaml
data_sources:
  dblp:
    enabled: true
    conferences: [sp, ccs, uss, ndss]
  nvd:
    enabled: true
    min_cvss_score: 7.0
  atum_blog:
    enabled: true
    days_back: 365
```

---

## 🤖 AI分析模块 (src/analyzers/)

### AIAnalyzer (`ai_analyzer.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 文章摘要生成 | ✅ | 生成中文摘要 |
| 技术分类 | ✅ | 自动分类标签 |
| 关键词提取 | ✅ | 提取核心关键词 |
| 中文翻译 | ✅ | 英文标题/摘要翻译 |
| 优先级评分 | ✅ | AI辅助评分 |

### 配置

```yaml
ai:
  enabled: true
  api_base: "${OPENAI_API_BASE}"
  api_key: "${OPENAI_API_KEY}"
  model: "gpt-4o-mini"
```

---

## 📊 优先级评分模块 (src/scoring/)

### PriorityScorer (`priority_scorer.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 来源权重评分 | ✅ | 不同来源不同权重 |
| AI辅助评分 | ✅ | 可选AI评估 |
| 批量评分 | ✅ | 高效批量处理 |
| 优先级排序 | ✅ | 按分数降序 |

### 默认权重

```yaml
source_weights:
  kev: 1.5      # 在野漏洞最高
  dblp: 1.3     # 顶会论文
  nvd: 1.2      # 高危漏洞
  huggingface: 1.1
  pwc: 1.1
  blog: 1.0
  arxiv: 1.0
  rss: 0.8
```

---

## 📤 推送模块 (src/pushers/)

### SmartSelector (`smart_selector.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 质量过滤 | ✅ | 按评分过滤 |
| 来源平衡 | ✅ | 避免单一来源过多 |
| 去重 | ✅ | 标题相似度去重 |
| 数量限制 | ✅ | 每日最多推送数 |
| 每日摘要 | ✅ | 生成统计摘要 |

### TieredPusher (`tiered_pusher.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 分级推送 | ✅ | 前10%/10-40%/其余 |
| 不同格式 | ✅ | 重要文章详细展示 |

---

## 💬 飞书交互模块 (src/bots/)

### FeishuBot (`feishu_bot.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| Webhook推送 | ✅ | 文本/卡片消息 |
| 文章卡片 | ✅ | 格式化文章展示 |
| 错误报告 | ✅ | 异常汇总推送 |

### FeishuBitable (`feishu_bitable.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 多维表格同步 | ✅ | 文章核心信息 |
| 自动创建表格 | ✅ | 首次运行自动创建 |
| 批量写入 | ✅ | 高效批量操作 |

### FeishuEventHandler (`feishu_event_handler.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 事件接收 | ✅ | 接收飞书消息事件 |
| 事件去重 | ✅ | 防止重复处理 |
| 消息解析 | ✅ | 解析@mention等 |
| 回复消息 | ✅ | 发送回复 |

### ThreadReplier (`thread_replier.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 线程回复 | ✅ | 在原消息下回复 |
| 低置信度提示 | ✅ | 标记不确定回答 |
| 来源引用 | ✅ | 显示参考来源 |

---

## 🧠 知识库问答模块 (src/qa/)

### KnowledgeBase (`knowledge_base.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 文章分块 | ✅ | 智能分块存储 |
| 向量化存储 | ✅ | ChromaDB |
| 语义搜索 | ✅ | 相似度检索 |
| 增量更新 | ✅ | 只添加新文章 |

### QAEngine (`qa_engine.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 问答生成 | ✅ | 基于检索的回答 |
| 上下文管理 | ✅ | 多轮对话 |
| 来源引用 | ✅ | 标注参考文章 |

### EnhancedRetriever (`enhanced_retriever.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 相似度过滤 | ✅ | 阈值过滤 |
| 结果去重 | ✅ | 内容去重 |
| 分块限制 | ✅ | 每文档最大分块数 |

### HistoryAwareQueryBuilder (`history_aware_query_builder.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 历史感知 | ✅ | 结合对话历史 |
| 查询重写 | ✅ | 优化检索查询 |

### EventServer (`event_server.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| HTTP服务器 | ✅ | 接收飞书事件 |
| 消息处理 | ✅ | 调用QA引擎 |
| 频率限制 | ✅ | 防止滥用 |

---

## 👤 用户反馈模块 (src/feedback/)

### FeedbackHandler (`feedback_handler.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 快速反馈 | ✅ | 有用/没用/收藏/更多 |
| 详细反馈 | ✅ | 原因说明 |
| 话题权重调整 | ✅ | 根据反馈调整 |
| 关键词偏好 | ✅ | 学习关键词偏好 |
| 用户画像 | ✅ | 构建用户偏好 |
| 来源权重调整 | ✅ | 调整来源可信度 |

### FeishuFeedbackHandler (`feishu_feedback.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 反馈命令解析 | ✅ | 识别反馈指令 |
| 对话式反馈 | ✅ | 多轮收集反馈 |
| 画像查询 | ✅ | 查看个人偏好 |
| 反馈卡片 | ✅ | 带按钮的卡片 |

### 反馈类型

```python
QuickRating:
  - USEFUL        # 有用 👍
  - NOT_USEFUL    # 没用 👎
  - BOOKMARK      # 收藏 ⭐
  - MORE_LIKE_THIS # 更多类似 🔍

NotMatchReason:
  - TOO_BASIC     # 太基础
  - TOO_ADVANCED  # 太深入
  - NOT_INTERESTED # 不感兴趣
  - LOW_QUALITY   # 质量差
```

---

## 📈 RSS评估模块 (src/evaluators/)

### RSSEvaluator (`rss_evaluator.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 活跃度检查 | ✅ | 6个月内是否更新 |
| 原创性评估 | ✅ | AI判断是否原创 |
| 技术深度评估 | ✅ | high/medium/low |
| 分类标签生成 | ✅ | 自动生成分类 |
| 综合评分 | ✅ | 0-1质量评分 |
| 评估报告 | ✅ | Markdown报告 |
| 筛选OPML导出 | ✅ | 导出高质量源 |
| 并发评估 | ✅ | 多线程加速 |
| 断点续传 | ✅ | 支持中断恢复 |

### 使用方式

```bash
# 评估RSS源
python main.py --evaluate --opml feeds.opml

# 输出
# - reports/evaluation_report.md
# - reports/filtered_feeds.opml
```

---

## 📊 统计分析模块 (src/stats/)

### StatsCollector (`collector.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 抓取统计 | ✅ | 记录抓取结果 |
| 推送统计 | ✅ | 记录推送情况 |
| 问答统计 | ✅ | 记录QA使用 |
| 页面浏览 | ✅ | 记录文章访问 |

### StatsStore (`store.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| SQLite存储 | ✅ | 持久化统计数据 |
| 时间序列 | ✅ | 按时间存储 |

### StatsAggregator (`aggregator.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 来源质量评估 | ✅ | 计算来源质量分 |
| 趋势分析 | ✅ | 时间趋势 |
| 热门话题 | ✅ | 话题排行 |

### TopicTracker (`topic_tracker.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 话题追踪 | ✅ | 追踪热门话题 |
| 突增检测 | ✅ | 检测话题突增 |
| 中文分词 | ✅ | jieba分词支持 |

### StatsAPI (`api.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 统计查询API | ✅ | 获取各类统计 |
| 缓存 | ✅ | 结果缓存 |

---

## 🔄 话题聚合模块 (src/aggregation/)

### AggregationEngine (`aggregation_engine.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 相似度计算 | ✅ | 标题+关键词 |
| 文章聚类 | ✅ | 相似文章分组 |
| AI相似度 | ✅ | 可选AI计算 |

### QualityFilter (`quality_filter.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 域名黑名单 | ✅ | 过滤低质量源 |
| 可信来源 | ✅ | 优先高质量源 |

### SynthesisGenerator (`synthesis_generator.py`)

| 功能 | 状态 | 说明 |
|------|------|------|
| 综述生成 | ✅ | AI生成话题综述 |

---

## ⏰ 调度器模块 (src/scheduler.py)

| 功能 | 状态 | 说明 |
|------|------|------|
| 定时执行 | ✅ | 每天指定时间 |
| 手动触发 | ✅ | --once参数 |
| 完整流程 | ✅ | 抓取→分析→推送 |
| 错误汇总 | ✅ | 推送错误报告 |
| 断点续传 | ✅ | 支持中断恢复 |

---

## 💾 数据存储

### SQLite数据库 (`data/articles.db`)

| 表 | 说明 |
|----|------|
| articles | 全部文章（完整内容） |
| article_feedback | 用户反馈记录 |
| feedback_insights | 反馈洞察 |
| topic_weights | 话题权重 |
| keyword_preferences | 关键词偏好 |
| user_profiles | 用户画像 |

### ChromaDB (`data/chroma_db/`)

- 向量知识库
- 文章分块存储
- 语义搜索索引

### 飞书多维表格

- 文章核心信息同步
- 可视化数据展示

---

## 🔧 工具脚本 (scripts/)

| 脚本 | 说明 |
|------|------|
| `quick_test.py` | 一键测试所有功能 |
| `full_test.py` | 完整流程测试 |
| `db_stats.py` | 数据库统计 |
| `init_knowledge_base.py` | 初始化知识库 |
| `sync_knowledge_base.py` | 同步知识库 |
| `run_qa_server.py` | 启动QA服务器 |
| `manual_push.py` | 手动推送 |
| `sync_to_bitable.py` | 同步到多维表格 |
| `evaluate_feeds.py` | 评估RSS源 |
| `merge_opml.py` | 合并OPML文件 |

---

## 🚀 飞书交互能力

### 已实现 ✅

1. **文章推送** - 自动推送优质文章到飞书群
2. **知识库问答** - @机器人 提问，基于知识库回答
3. **用户反馈** - 对文章进行有用/没用等反馈
4. **查看画像** - 查看个人偏好画像
5. **错误报告** - 自动推送抓取错误

### 待实现 🔜

1. **通过飞书添加RSS源** - 发送RSS链接自动添加
2. **通过飞书管理订阅** - 查看/删除订阅源
3. **通过飞书触发抓取** - 手动触发一次抓取

---

## 📋 配置清单

### 必需配置

```env
# .env 文件
OPENAI_API_KEY=your-api-key
FEISHU_WEBHOOK_URL=your-webhook-url
```

### 可选配置

```env
FEISHU_APP_ID=           # 飞书应用ID（双向交互需要）
FEISHU_APP_SECRET=       # 飞书应用密钥
FEISHU_BITABLE_APP_TOKEN= # 多维表格Token
FEISHU_VERIFICATION_TOKEN= # 事件验证Token
GITHUB_TOKEN=            # GitHub API Token
NVD_API_KEY=             # NVD API Key
```

---

## 🧪 测试

### 运行测试

```bash
# 快速测试
python scripts/quick_test.py

# 完整测试
python scripts/full_test.py

# 单元测试
python -m pytest tests/ -v
```

### 测试覆盖

- ✅ 模块导入测试
- ✅ 配置加载测试
- ✅ 数据库连接测试
- ✅ RSS抓取测试
- ✅ 网页博客抓取测试
- ✅ AI分析器测试
- ✅ QA系统测试
- ✅ 统计系统测试
- ✅ 飞书机器人测试

---

## 📝 后续计划

### 短期 (1-2周)

- [ ] 通过飞书添加RSS源功能
- [ ] 通过飞书管理订阅功能
- [ ] 完善错误处理和重试机制

### 中期 (1个月)

- [ ] 更智能的文章去重
- [ ] 基于反馈的推荐优化
- [ ] 更多数据源支持

### 长期

- [ ] 多用户支持
- [ ] 更精细的权限控制
- [ ] 性能优化

---

## 📞 使用方式

### 启动定时任务

```bash
python main.py
```

### 手动执行一次

```bash
python main.py --once
```

### 评估RSS源

```bash
python main.py --evaluate --opml feeds.opml
```

### 启动QA服务器

```bash
python scripts/run_qa_server.py
```

---

## 📚 相关文档

- [USAGE.md](USAGE.md) - 使用说明书
- [README.md](README.md) - 项目简介
- [config.yaml](config.yaml) - 配置文件

