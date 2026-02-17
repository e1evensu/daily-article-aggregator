# 每日文章聚合器

技术内容聚合系统，多源数据抓取 + AI 实时评分 + 飞书推送。

## 数据源 (600+)

| 数据源 | 说明 |
|--------|------|
| RSS | `reports/filtered_feeds.opml` (654个评估后的高质量源) |
| HN Top 90 | Andrej Karpathy 推荐的技术博客 |
| arXiv | 论文 (cs.AI/cs.CR/cs.CL) |
| DBLP | 安全四大顶会 (S&P/CCS/USENIX/NDSS) |
| NVD | CVE 漏洞库 |
| KEV | CISA 在野利用漏洞 |
| HuggingFace | 热门论文 |
| Papers With Code | 带代码的论文 |
| 大厂博客 | OpenAI/DeepMind/Anthropic |
| GitHub Trending | 安全/AI 相关热门项目 |

## 核心功能

### AI 实时评分
- 三维评分: relevance / quality / timeliness
- 六大分类: AI/ML、安全、工程、工具/开源、观点/杂谈、Other
- 关键词提取
- 批量评分

### 分级推送 (按百分比)
- 🔥 **前 10%**: 重点推荐 (完整摘要)
- ⭐ **10%-30%**: 推荐 (简要摘要)
- 📋 **30%-60%**: 其他 (标题列表)
- **后 40%**: 不推送

### 交互式卡片消息
- 推送带反馈按钮的消息卡片
- 用户可直接点击评价：👍 有用 / 👎 没用 / ⭐ 收藏
- 实时反馈记录到数据库

### AI 分析
- 摘要生成 + 中文翻译
- 分类标签
- 漏洞评估
- 关键词提取
- 话题聚合与总结

### 云文档发布
- 自动创建飞书云文档
- 文档链接存入多维表格
- 支持历史文章检索

### 知识库问答
- 基于 ChromaDB 向量知识库
- 支持用户提问相关文章
- 会话上下文记忆

### PDF 论文翻译
- 支持arXiv论文PDF全文翻译
- 图表理解与描述
- 飞书通知翻译完成

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 复制环境配置
cp .env.example .env

# 编辑 .env 填入 API Key
# OPENAI_API_KEY=xxx
# FEISHU_WEBHOOK_URL=xxx
# FEISHU_APP_ID=xxx
# FEISHU_APP_SECRET=xxx
# FEISHU_CHAT_ID=xxx

# 单次执行测试
python main.py --once

# 定时运行 (每天 07:00)
python main.py
```

## 服务器部署

```bash
tmux new -s daily
python3.10+ main.py
# Ctrl+B D 退出
```

## 项目结构

```
src/
├── fetchers/           # 数据抓取 (RSS/arXiv/DBLP/NVD/KEV...)
├── analyzers/         # AI 分析 (摘要/翻译/分类)
├── scoring/           # AI 实时评分 (ai_scorer.py)
├── pushers/           # 分级推送 (tiered_pusher.py)
├── bots/              # 飞书机器人/多维表格/云文档
├── aggregation/       # 话题聚合
├── qa/                # 知识库问答
├── stats/             # 统计分析
├── evaluators/        # RSS 源评估
├── feedback/          # 用户反馈处理
├── paper_translator/  # PDF 论文翻译
└── scheduler.py       # 定时调度
```

## 配置文件

### 环境变量 (.env)
```
OPENAI_API_KEY=
FEISHU_WEBHOOK_URL=
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_CHAT_ID=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
```

### config.yaml 关键配置

```yaml
# RSS 源 (使用评估后的筛选源)
sources:
  rss:
    opml_path: "reports/filtered_feeds.opml"

# 交互式卡片消息（带反馈按钮）
tiered_push:
  use_interactive_card: true

# AI 实时评分
ai_scorer:
  enabled: true
  batch_size: 10

# 分级推送 (百分比)
tiered_push:
  level1_threshold: 0.10   # 前10%
  level2_threshold: 0.30  # 10%-30%
  level3_threshold: 0.60   # 30%-60%

# 知识库问答
knowledge_qa:
  enabled: true

# 话题聚合
topic_aggregation:
  enabled: true

# PDF 翻译
pdf_translation:
  enabled: true

# 漏洞过滤
vulnerability_filter:
  enabled: true

# 调度
schedule:
  time: "07:00"
```

## 更新日志

### 2026-02
- 新增交互式卡片消息（带反馈按钮）
- 新增用户反馈系统（有用/没用/收藏）
- 新增云文档自动发布
- 新增多维表格存储（包含文档链接）
- 新增知识库问答系统（ChromaDB向量库）
- 新增PDF论文翻译功能
- 新增GitHub Trending数据源
- 新增漏洞过滤系统
- 迁移到飞书应用中心API（支持更丰富消息类型）

### 2025-02
- 新增 AI 实时三维评分 (relevance/quality/timeliness)
- 改用 filtered_feeds.opml (654个高质量源)
- 分级推送改为按百分比 (10%/20%/30%/40%)
- 添加 HN Top 90 博客 RSS 源
