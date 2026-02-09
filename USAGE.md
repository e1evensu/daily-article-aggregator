# Daily Article Aggregator 使用说明书

## 📋 目录

1. [项目简介](#项目简介)
2. [核心功能](#核心功能)
3. [快速开始](#快速开始)
4. [配置说明](#配置说明)
5. [一键测试](#一键测试)
6. [日常使用](#日常使用)
7. [高级功能](#高级功能)
8. [常见问题](#常见问题)

---

## 项目简介

Daily Article Aggregator 是一个智能文章聚合系统，核心功能：

1. **RSS源评估** - 自动评估RSS订阅源质量，筛选保留可用源
2. **自动抓取分析** - 每天定时抓取RSS源，AI分析评估，推送优质文章到飞书
3. **完整存储** - 存储全部文章（完整内容）到SQLite数据库，核心信息同步到飞书多维表格
4. **知识库问答** - 文章加入向量知识库（ChromaDB），支持通过飞书对话分析知识库内容
5. **RSS源扩展** - 通过原有RSS源不断优化，获取更多RSS源
6. **错误监控** - 飞书推送错误报告，方便快速发现和修复问题

---

## 核心功能

### 1️⃣ RSS源评估

评估订阅源质量，自动筛选保留高质量源：

```bash
# 评估RSS源质量
python main.py --evaluate --opml feeds.opml

# 指定最低评分阈值
python main.py --evaluate --opml feeds.opml --min-score 0.7
```

评估结果：
- `reports/evaluation_report.md` - 详细评估报告
- `reports/filtered_feeds.opml` - 筛选后的高质量订阅源

### 2️⃣ 自动抓取与推送

每天定时执行完整流程：抓取 → AI分析 → 评分筛选 → 推送到飞书

支持的数据源：
- RSS/Atom 订阅
- arXiv 论文
- DBLP 安全顶会论文
- NVD/KEV 漏洞数据库
- HuggingFace/Papers With Code 论文
- GitHub 热门项目
- 大厂技术博客（OpenAI、Anthropic、DeepMind、腾讯混元、Atum等）

### 3️⃣ 数据存储

- **SQLite数据库** (`data/articles.db`) - 存储全部文章完整内容
- **飞书多维表格** - 同步核心信息（标题、摘要、分类、链接等）

### 4️⃣ 知识库问答

基于 ChromaDB 向量数据库的智能问答：
- 文章自动分块、向量化存储
- 支持语义搜索
- 通过飞书机器人对话查询

### 5️⃣ 错误监控

抓取过程中的错误会自动汇总推送到飞书，包括：
- 数据源名称
- 错误信息
- 任务耗时

---

## 快速开始

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd daily-article-aggregator
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制环境变量模板并填写：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# OpenAI API（必需，用于AI分析）
OPENAI_API_KEY=your-openai-api-key
OPENAI_BASE_URL=https://api.openai.com/v1

# 飞书配置（必需，用于推送）
FEISHU_WEBHOOK_URL=your-feishu-webhook-url
FEISHU_APP_ID=your-app-id
FEISHU_APP_SECRET=your-app-secret

# 飞书多维表格（可选）
FEISHU_BITABLE_APP_TOKEN=
FEISHU_BITABLE_TABLE_ID=

# 飞书事件服务器（可选，用于QA问答）
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=

# GitHub Token（可选，用于抓取GitHub热门项目）
GITHUB_TOKEN=

# NVD API Key（可选，用于抓取漏洞数据）
NVD_API_KEY=
```

### 4. 一键测试

```bash
python scripts/quick_test.py
```

---

## 配置说明

主配置文件: `config.yaml`

### 核心配置项

```yaml
# 数据库
database:
  path: data/articles.db

# AI配置
ai:
  enabled: true
  api_key: ${OPENAI_API_KEY}
  model: gpt-4o-mini

# 飞书推送
feishu:
  webhook_url: ${FEISHU_WEBHOOK_URL}

# 飞书多维表格
feishu_bitable:
  enabled: true
  app_id: ${FEISHU_APP_ID}
  app_secret: ${FEISHU_APP_SECRET}

# 调度时间
schedule:
  time: "07:00"
  timezone: "Asia/Shanghai"

# 知识库问答
knowledge_qa:
  enabled: true
  chroma:
    path: "data/chroma_db"
    collection_name: "knowledge_articles"
```

---

## 一键测试

### 基础测试

```bash
python scripts/quick_test.py
```

测试内容：
- ✅ 模块导入检查
- ✅ 配置文件加载
- ✅ 数据库连接
- ✅ RSS抓取功能
- ✅ 网页博客抓取（Atum等）
- ✅ AI分析器
- ✅ QA系统
- ✅ 统计系统
- ✅ 飞书机器人

### 完整流程测试

```bash
python scripts/quick_test.py --full
```

### 运行单元测试

```bash
python -m pytest tests/ -v
```

---

## 日常使用

### 启动定时调度（推荐）

```bash
python main.py
```

程序会在每天配置的时间（默认07:00）自动执行：
1. 抓取所有数据源
2. AI分析新文章
3. 智能筛选优质文章
4. 推送到飞书
5. 同步到多维表格
6. 更新知识库

### 手动执行一次

```bash
python main.py --once
```

### 评估RSS源

```bash
python main.py --evaluate --opml feeds.opml
```

### 查看断点状态

```bash
python main.py --checkpoint-status
```

### 清除断点

```bash
python main.py --clear-checkpoint
```

### 查看数据库统计

```bash
python scripts/db_stats.py
```

---

## 飞书交互功能

### 知识库问答

通过飞书与机器人对话，查询知识库中的内容：

1. 在飞书群中 @机器人
2. 输入问题，如："最近有什么关于LLM安全的文章？"
3. 机器人会基于知识库回答，并附上参考来源

### 用户反馈

对推送的文章进行反馈，系统会学习你的偏好：

```
有用      - 标记文章有价值，增加类似内容推荐
没用      - 标记文章无价值，减少类似内容
收藏      - 收藏重要文章
更多      - 希望看到更多类似内容
```

详细反馈原因：
- 太基础 - 系统会推荐更深入的内容
- 太深 - 系统会推荐更基础的内容
- 不感兴趣 - 减少该话题推荐
- 质量差 - 降低该来源权重

### 查看个人画像

发送以下命令查看你的偏好画像：

```
我的画像
用户画像
反馈统计
```

---

## 高级功能

### 知识库管理

```bash
# 初始化/更新知识库（将文章导入向量数据库）
python scripts/init_knowledge_base.py

# 同步最新文章到知识库
python scripts/sync_knowledge_base.py
```

### 启动QA服务器

启动飞书事件服务器，接收飞书消息并回复：

```bash
python scripts/run_qa_server.py
```

### 手动推送

```bash
python scripts/manual_push.py
```

### 飞书多维表格同步

```bash
python scripts/sync_to_bitable.py
```

### 话题聚合

自动聚合相关文章生成专题报告：

```bash
python scripts/run_topic_aggregation.py
```

---

## 数据源配置

### RSS订阅

订阅文件位置: `rss/` 目录下的 `.opml` 文件

添加新订阅，编辑 `rss/CustomRSS.opml`：

```xml
<outline title="博客名称" text="博客名称" 
         htmlUrl="https://example.com" 
         xmlUrl="https://example.com/feed.xml" 
         type="rss" />
```

### 网页博客（无RSS）

对于没有RSS的博客，系统支持直接抓取网页。

已内置支持：
- **腾讯混元研究** (hunyuan)
- **Anthropic Red Team** (anthropic_red)
- **Atum Blog** (atum_blog) - https://atum.li/cn/

在 `config.yaml` 中启用：

```yaml
data_sources:
  atum_blog:
    enabled: true
    timeout: 30
    days_back: 365
```

---

## 目录结构

```
daily-article-aggregator/
├── main.py              # 主程序入口
├── config.yaml          # 配置文件
├── requirements.txt     # Python依赖
├── .env                 # 环境变量(需自行创建)
├── data/                # 数据目录
│   ├── articles.db      # SQLite数据库（全部文章）
│   └── chroma_db/       # 向量知识库
├── rss/                 # RSS订阅文件
├── src/                 # 源代码
│   ├── fetchers/        # 数据抓取器
│   ├── analyzers/       # AI分析器
│   ├── pushers/         # 推送器
│   ├── qa/              # QA问答系统
│   ├── stats/           # 统计分析
│   ├── bots/            # 飞书机器人
│   └── aggregation/     # 话题聚合
├── scripts/             # 工具脚本
│   ├── quick_test.py    # 一键测试
│   └── ...
├── tests/               # 测试文件
└── reports/             # 评估报告
```

---

## 常见问题

### Q: 数据库锁定错误

**错误**: `sqlite3.OperationalError: database is locked`

**解决**: 已内置重试机制和WAL模式，如仍有问题，检查是否有多个进程同时访问数据库。

### Q: OpenAI API调用失败

**检查**:
1. API Key是否正确配置
2. 网络是否能访问API
3. 是否超出配额

### Q: 飞书推送失败

**检查**:
1. Webhook URL是否正确
2. 机器人是否在群内
3. 消息格式是否正确

### Q: RSS抓取为空

**可能原因**:
1. RSS源不可访问
2. 网络问题
3. RSS格式不标准

---

## 联系与支持

如有问题，请提交Issue或联系维护者。
