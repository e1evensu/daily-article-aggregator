下面按你给的 7 个重点分析。代码引用均基于当前目录 `/home/suuuu/develop/intelligence-system/archive/picker`。

**整体架构**
`picker` 是一个以 GitHub Actions 为调度器、GitHub Issues 为交互与存储界面、Bot 为通知出口、`archive` 分支/目录为长期归档的 RSS 安全资讯聚合系统。核心代码集中在：

- [picker.py](/home/suuuu/develop/intelligence-system/archive/picker/picker.py:1)：主流程、RSS 抓取、Issue 联动、标签初始化、归档入口。
- [ai.py](/home/suuuu/develop/intelligence-system/archive/picker/ai.py:22)：文章抓取、HTML 转 Markdown、AI 摘要和分类。
- [bot.py](/home/suuuu/develop/intelligence-system/archive/picker/bot.py:47)：飞书、企业微信、钉钉、QQ、邮件通知实现。
- [config.yml](/home/suuuu/develop/intelligence-system/archive/picker/config.yml:1)：订阅源、代理、Bot、AI 配置。
- `.github/workflows/*.yml`：自动化调度与 Issue 事件管线。

**1. RSS/OPML 订阅管理和 Feed 解析流程**
订阅源在 [config.yml](/home/suuuu/develop/intelligence-system/archive/picker/config.yml:9) 的 `rss:` 下声明，每个源有 `enabled`、`filename`，可选 `url`。本地 OPML 放在 `rss/*.opml`，例如 [rss/CustomRSS.opml](/home/suuuu/develop/intelligence-system/archive/picker/rss/CustomRSS.opml:1)。

订阅更新流程在 [picker.py](/home/suuuu/develop/intelligence-system/archive/picker/picker.py:152)：

- `update_rss(rss, proxy_url)`：如果配置了远程 `url`，用 `requests.get()` 拉取 OPML 并写入 `rss/{filename}`。
- 如果远程更新失败但本地文件存在，回退使用旧 OPML。
- 没有 `url` 的源被视为本地 OPML。

订阅初始化在 [picker.py](/home/suuuu/develop/intelligence-system/archive/picker/picker.py:354) 的 `init_rss()`：

```python
enabled = [{k: v} for k, v in conf.items() if v['enabled']]
rss = listparser.parse(open(file, encoding="utf-8").read())
for feed in rss.feeds:
    url = feed.url.strip().rstrip('/')
```

这里使用 `listparser` 解析 OPML，提取每个 `outline` 的 RSS URL。去重逻辑是把 URL 去掉协议和 `www.` 后用包含判断做粗粒度去重。

Feed 解析在 [picker.py](/home/suuuu/develop/intelligence-system/archive/picker/picker.py:317) 的 `parse_rss()`：

- `requests.get(url)` 获取 RSS/Atom 内容。
- `feedparser.parse(r.content)` 解析。
- 取 `r.feed.title` 作为来源名。
- 遍历 `r.entries`，优先用 `published_parsed`，否则用 `updated_parsed`。
- 只保留发布日期等于“昨天”的文章。
- 返回结构是 `(feed_title, {entry.title: entry.link})`。

**2. picker.py 主流程：抓取到处理到推送**
入口在 [picker.py](/home/suuuu/develop/intelligence-system/archive/picker/picker.py:730)。启动时读取 `config.yml`，初始化两组 Bot：

```python
bots = init_bot(conf['bot'], proxy_bot)
picker_bots = init_bot(conf["pick_bot"], proxy_bot, True)
```

主任务默认进入 [rssjob()](/home/suuuu/develop/intelligence-system/archive/picker/picker.py:387)：

1. 读取代理配置。
2. `init_rss()` 聚合所有启用 OPML 中的 feed URL。
3. 初始化 AI 处理器，取决于 `conf['ai']['enabled']` 和 `mode`。
4. 使用 `ThreadPoolExecutor(100)` 并发抓取所有 feed。
5. 汇总为：

```python
results = {
  "Feed Title": {
    "Article Title": "https://article-url"
  }
}
```

6. 如果 AI 模式是 `daily`，对所有文章执行 AI 摘要，结果变成：

```python
{
  "Article Title": {
    "url": "...",
    "summary": "...",
    "category": "...",
    "markdown_content": "..."
  }
}
```

7. 写入 `archive/{year}/{month}/{day}/daily.json`。
8. 调用 `update_today(results)` 生成根目录 `today.md` 和归档目录 `daily.md`。
9. 通过 `bots` 发送每日信息流。
10. 发送一条摘要通知，说明本次从多少 feed 抓到了多少文章。

GitHub Actions 的每日任务在 [.github/workflows/daily.yml](/home/suuuu/develop/intelligence-system/archive/picker/.github/workflows/daily.yml:45) 调用：

```bash
python3 picker.py
gh issue create --title "[每日信息流] $(date +'%Y-%m-%d')" -F today.md --label "daily"
```

所以每日信息流既会推 Bot，也会变成一个 `daily` Issue。

**3. ai.py 的 AI 集成：分析、摘要、分类**
AI 核心类是 [ArticleProcessor](/home/suuuu/develop/intelligence-system/archive/picker/ai.py:22)。配置来源在 [ai.py](/home/suuuu/develop/intelligence-system/archive/picker/ai.py:43)：

- API Key：环境变量 `OPENAI_API_KEY` 或 `config.yml` 的 `ai.api_key`
- API Base：默认 OpenAI 兼容 `/v1`，当前配置是 Moonshot：[config.yml](/home/suuuu/develop/intelligence-system/archive/picker/config.yml:95)
- Model：默认/配置为 `kimi-k2-0905-preview`
- prompt：系统提示词要求输出主题、关键点、应用场景、局限性、评价。

完整处理链在 [ai.py](/home/suuuu/develop/intelligence-system/archive/picker/ai.py:277)：

```python
fetch_article_content(url)
html_to_markdown(html_content)
generate_summary(title, markdown_content)
generate_category(title, summary)
```

文章抓取使用浏览器 UA，并支持代理失败后的重试：[ai.py](/home/suuuu/develop/intelligence-system/archive/picker/ai.py:69)。HTML 转 Markdown 使用 `markitdown`：[ai.py](/home/suuuu/develop/intelligence-system/archive/picker/ai.py:138)。摘要调用 OpenAI-compatible Chat Completions：[ai.py](/home/suuuu/develop/intelligence-system/archive/picker/ai.py:159)。

分类调用单独的 prompt，让模型只能从 13 个安全分类中选一个：[ai.py](/home/suuuu/develop/intelligence-system/archive/picker/ai.py:204)。返回值会进入 `category` 字段，并在 Issue 总结流程中转成 GitHub label。

精选 Issue 的 AI 总结入口是 [summarize_issue()](/home/suuuu/develop/intelligence-system/archive/picker/picker.py:581)：

- 读取 Issue body 第一行 URL。
- 调 `ArticleProcessor.process_article()`。
- 把原文 Markdown 和 AI 摘要写回 Issue body。
- 保存文章 Markdown 和摘要 Markdown。
- 根据分类添加 GitHub label。
- 向 `picker_bots` 推送摘要通知。

**4. bot.py 通知系统：渠道和消息格式**
Bot 初始化在 [bot.py](/home/suuuu/develop/intelligence-system/archive/picker/bot.py:47)。支持的实现类是：

- `feishuBot`：飞书群机器人。
- `wecomBot`：企业微信机器人。
- `dingtalkBot`：钉钉机器人。
- `qqBot`：基于 `go-cqhttp` 的 QQ 群机器人。
- `mailBot`：邮件。

配置里有 `telegram`，README 也提到 Telegram，但 [bot.py](/home/suuuu/develop/intelligence-system/archive/picker/bot.py:28) 的 `__all__` 和 `init_bot()` 没有 Telegram 分支，因此当前代码实际没有 Telegram 实现。

每日信息流消息格式主要是 Markdown 列表。飞书和钉钉都支持新旧数据格式：旧格式 `{title: url}`，新格式 `{title: {url, summary}}`，如果有摘要会追加引用块：

```python
- [title](link)
  > summary
```

对应代码在 [bot.py](/home/suuuu/develop/intelligence-system/archive/picker/bot.py:132) 和 [bot.py](/home/suuuu/develop/intelligence-system/archive/picker/bot.py:246)。

精选通知格式是：

```markdown
[YYYY-MM-DD 精选] Feed:
  - [title](link) - [discussion](issue_url)
```

钉钉发送使用 markdown 消息并带 HMAC 签名：[bot.py](/home/suuuu/develop/intelligence-system/archive/picker/bot.py:276)。企业微信使用 `msgtype=markdown`。邮件输出 HTML。QQ 输出纯文本标题和链接。

**5. GitHub Issues 作为存储和交互层**
Issue 分三类基础标签：

- `daily`：每日信息流 Issue，由 [.github/workflows/daily.yml](/home/suuuu/develop/intelligence-system/archive/picker/.github/workflows/daily.yml:60) 创建。
- `dailypick`：每日精选汇总 Issue，由 [.github/workflows/pick.yml](/home/suuuu/develop/intelligence-system/archive/picker/.github/workflows/pick.yml:58) 创建。
- `pick`：单篇精选文章 Issue，由用户手动创建或从每日信息流 Convert to issue。

当用户打开无标签 Issue 时，[.github/workflows/issue.yml](/home/suuuu/develop/intelligence-system/archive/picker/.github/workflows/issue.yml:8) 会自动：

- 给 Issue 加 `pick` 标签。
- 把标题改成 `[YYYY-MM-DD] 原标题`。
- 调用 `python3 picker.py --push-issue <number>` 推送精选通知。
- 再调用 `python3 picker.py --summarize-issue <number>` 生成 AI 摘要。

`push_issue()` 会尝试在当天 `daily.json` 中按标题匹配文章：[picker.py](/home/suuuu/develop/intelligence-system/archive/picker/picker.py:272)。匹配成功则把 Issue body 改成：

```markdown
FeedName: [IssueTitle](ArticleURL)
```

匹配失败则认为是手动新增精选，直接用 Issue body 里的 URL 推送。

评论通知由 [.github/workflows/comment.yml](/home/suuuu/develop/intelligence-system/archive/picker/.github/workflows/comment.yml:1) 处理，只对带 `pick` 标签的 Issue 生效，发送到钉钉。

**6. 13 个安全分类标签的设计和用途**
分类映射在 [picker.py](/home/suuuu/develop/intelligence-system/archive/picker/picker.py:25) 的 `CATEGORY_LABELS`：

- `Red Team` → `red-team`：红队技术。
- `Blue Team` → `blue-team`：蓝队防御。
- `Web Security` → `web-security`：Web 安全。
- `Binary Security` → `binary-security`：二进制安全。
- `Mobile Security` → `mobile-security`：移动安全。
- `Cloud Security` → `cloud-security`：云安全。
- `AI Security` → `ai-security`：AI 安全。
- `Vulnerability Analysis` → `vulnerability`：漏洞分析。
- `Reverse Engineering` → `reverse-engineering`：逆向工程。
- `Code Audit` → `code-audit`：代码审计。
- `Security Tools` → `security-tools`：安全工具。
- `Security Research` → `security-research`：安全研究。
- `Others` → `others`：兜底分类。

`--init` 会调用 [init_labels()](/home/suuuu/develop/intelligence-system/archive/picker/picker.py:43)，通过 `gh label list/create/edit` 创建或更新这些标签。AI 分类产生后，[summarize_issue()](/home/suuuu/develop/intelligence-system/archive/picker/picker.py:687) 会把分类映射成 label 并添加到精选 Issue 上。这样 Issues 同时承担“讨论区”和“按安全领域检索的知识库索引”。

**7. archive 归档系统目录结构**
标准路径由 [get_archive_paths()](/home/suuuu/develop/intelligence-system/archive/picker/picker.py:92) 统一生成：

```text
archive/{year}/{month}/{day}/
├── daily.json
├── daily.md
├── pick.md
├── daily/
├── summary/
└── pick/
```

`daily.json` 保存当天抓取结构；`daily.md` 是每日信息流 Markdown；`pick.md` 是精选汇总；`daily/` 保存文章正文 Markdown；`summary/` 保存 AI 摘要和参考链接。README 也描述了同样结构：[README.md](/home/suuuu/develop/intelligence-system/archive/picker/README.md:250)。

文章 Markdown 保存逻辑在 [ai.py](/home/suuuu/develop/intelligence-system/archive/picker/ai.py:387)。文件名模式是：

```text
daily/{source}_{title}.md
summary/{source}_{title}_summary.md
```

每个文件带 YAML frontmatter，例如 `title/url/source/date/fetch_date/category`。摘要文件还会从正文 Markdown 中提取链接，追加 `## 参考链接`：[ai.py](/home/suuuu/develop/intelligence-system/archive/picker/ai.py:451)。

GitHub Actions 会把生成的 `archive/{year}/{month}/{day}` 提交到独立的 `archive` 分支，而不是长期堆在 `master`：[.github/workflows/daily.yml](/home/suuuu/develop/intelligence-system/archive/picker/.github/workflows/daily.yml:65)、[.github/workflows/pick.yml](/home/suuuu/develop/intelligence-system/archive/picker/.github/workflows/pick.yml:66)、[.github/workflows/issue.yml](/home/suuuu/develop/intelligence-system/archive/picker/.github/workflows/issue.yml:82)。

补充两个实现风险：`update_pick()` 里使用了 `paths['pick']`，但 `get_archive_paths()` 返回的是 `pick_dir`，这里会触发 KeyError；另外 `push_issue()` 仍按旧格式把 `articles.items()` 的 value 当 URL 使用，若 `daily.json` 已经是 AI 新格式 dict，Issue body 可能写入 dict 字符串。