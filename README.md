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

### AI 分析
- 摘要生成 + 中文翻译
- 分类标签
- 漏洞评估
- 关键词提取

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 复制环境配置
cp .env.example .env

# 编辑 .env 填入 API Key
# OPENAI_API_KEY=xxx
# FEISHU_WEBHOOK_URL=xxx

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
├── bots/              # 飞书机器人/多维表格
├── aggregation/       # 话题聚合
├── qa/                # 知识库问答
├── stats/             # 统计分析
├── evaluators/        # RSS 源评估
└── scheduler.py       # 定时调度
```

## 配置文件

### 环境变量 (.env)
```
OPENAI_API_KEY=
FEISHU_WEBHOOK_URL=
FEISHU_APP_ID=
FEISHU_APP_SECRET=
```

### config.yaml 关键配置

```yaml
# RSS 源 (使用评估后的筛选源)
sources:
  rss:
    opml_path: "reports/filtered_feeds.opml"

# AI 实时评分
ai_scorer:
  enabled: true
  batch_size: 10

# 分级推送 (百分比)
tiered_push:
  level1_threshold: 0.10   # 前10%
  level2_threshold: 0.30   # 10%-30%
  level3_threshold: 0.60   # 30%-60%

# 调度
schedule:
  time: "07:00"
```

## 更新日志

### 2025-02
- 新增 AI 实时三维评分 (relevance/quality/timeliness)
- 改用 filtered_feeds.opml (654个高质量源)
- 分级推送改为按百分比 (10%/20%/30%/40%)
- 添加 HN Top 90 博客 RSS 源
