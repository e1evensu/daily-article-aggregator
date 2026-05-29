**整体架构**
`yupi-hot-monitor` 是一个前后端分离的热点监控系统：后端负责关键词轮询、多源抓取、AI 过滤分析、入库、通知推送；前端负责关键词管理、实时热点流、筛选排序和通知展示。

核心技术栈：

- 后端：Express 5.2、TypeScript、Prisma 6、SQLite、Socket.io、node-cron、Nodemailer、OpenRouter SDK。依赖见 [server/package.json](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/package.json:21)。
- 前端：React 19.2、Vite 7、Tailwind CSS 4、Framer Motion、Lucide、socket.io-client。依赖见 [client/package.json](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/client/package.json:12)。
- 数据模型：`Keyword`、`Hotspot`、`Notification`、`Setting` 四张核心表，见 [server/prisma/schema.prisma](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/prisma/schema.prisma:13)。
- 运行入口：Express 路由、HTTP Server、Socket.io、定时任务都在 [server/src/index.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/index.ts:17) 初始化。
- 本地开发：Vite 将 `/api` 和 `/socket.io` 代理到 `localhost:3001`，见 [client/vite.config.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/client/vite.config.ts:8)。

**1. Express 5 + React 19 + OpenRouter + Socket.io**
后端入口模式很直接：`express()` 创建 REST API，`createServer(app)` 包一层 HTTP Server，再把 Socket.io 绑定到同一个 server 上，见 [server/src/index.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/index.ts:17)。REST 路由分为：

- `/api/keywords`：关键词增删改查和激活/暂停。
- `/api/hotspots`：热点列表、统计、手动搜索、删除。
- `/api/settings`：KV 设置。
- `/api/notifications`：站内通知。

定时任务使用 `node-cron` 每 30 分钟执行一次 `runHotspotCheck(io)`，同时也暴露 `/api/check-hotspots` 手动触发，见 [server/src/index.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/index.ts:41) 和 [server/src/index.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/index.ts:69)。

AI 层使用 `@openrouter/sdk`，初始化在 [server/src/services/ai.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/ai.ts:4)，当前模型固定为 `deepseek/deepseek-v3.2`，用于查询扩展和内容分析。

前端是一个单页 React 应用，主要状态集中在 [client/src/App.tsx](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/client/src/App.tsx:48)，通过 `services/api.ts` 调 REST，通过 `services/socket.ts` 订阅实时事件。

**2. 多数据源聚合抓取**
项目的统一数据结构是 `SearchResult`，它把不同平台结果归一成 `title/content/url/source/sourceId/publishedAt/互动数据/作者信息`，见 [server/src/types.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/types.ts:1)。类型层支持 8 个来源：

`twitter | bing | google | duckduckgo | hackernews | sogou | bilibili | weibo`

实际定时监控主链路当前并行调用 6 个来源：Twitter、Bing、Hacker News、搜狗、B站、微博，并额外做 B站账号检测，见 [server/src/jobs/hotspotChecker.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/jobs/hotspotChecker.ts:76)。Google 和 DuckDuckGo 已在通用搜索服务中实现，但没有被 `runHotspotCheck` 当前主任务调用，见 [server/src/services/search.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/search.ts:85) 和 [server/src/services/search.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/search.ts:131)。

各源接入模式：

- Twitter：走 `twitterapi.io` REST API，构造高级搜索语法，Top 拉近 7 天、Latest 拉近 3 天，排除转推/回复，Top 加 `min_faves:10`，见 [server/src/services/twitter.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/twitter.ts:63)。结果再按点赞、转发、浏览、粉丝数、本地蓝 V 权重过滤排序，见 [server/src/services/twitter.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/twitter.ts:20)。
- Bing：`axios + cheerio` 抓 HTML，解析 `li.b_algo`、`h2 a`、`.b_caption p`，见 [server/src/services/search.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/search.ts:40)。
- Google：同样 HTML 抓取，解析 `div.g`、`h3`、`.VwiC3b`，见 [server/src/services/search.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/search.ts:85)。
- DuckDuckGo：抓 `html.duckduckgo.com/html/`，解析 `.result`，并从 `uddg=` 重定向参数还原真实 URL，见 [server/src/services/search.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/search.ts:131)。
- Hacker News：调用 Algolia API，限制 `created_at_i` 最近 24 小时，映射 points/comments/author，见 [server/src/services/search.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/search.ts:200)。
- 搜狗：HTML 抓取 `https://www.sogou.com/web`，解析 `.vrwrap, .rb`，过滤“大家还在搜”，见 [server/src/services/chinaSearch.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/chinaSearch.ts:42)。
- Bilibili：公开 API 搜视频，按 `pubdate` 排序，并携带随机 `buvid3` cookie 规避 412，见 [server/src/services/chinaSearch.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/chinaSearch.ts:170)。还支持用户搜索和空间最新视频抓取，见 [server/src/services/chinaSearch.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/chinaSearch.ts:228)。
- 微博：使用 `https://weibo.com/ajax/side/hotSearch` 热搜 API，按查询词与热搜词双向包含匹配，见 [server/src/services/chinaSearch.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/chinaSearch.ts:341)。

聚合后的处理顺序是：账号内容优先加入 → 多源 `Promise.allSettled` 容错聚合 → URL 去重 → 7 天新鲜度过滤 → 来源优先级排序 → 分来源配额处理。关键代码在 [server/src/jobs/hotspotChecker.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/jobs/hotspotChecker.ts:119)。去重逻辑按标准化 URL 去尾斜杠和 `www.`，见 [server/src/services/search.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/search.ts:241)。

**3. AI 分析管线**
AI 管线分四层：

1. 查询扩展  
`expandKeyword()` 先用本地 `extractCoreTerms()` 从空格、连字符、下划线等拆核心词；如果配置了 `OPENROUTER_API_KEY`，再调用 OpenRouter 让模型输出 5-15 个关键词变体，结果用 `Map` 缓存，见 [server/src/services/ai.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/ai.ts:15)。

2. 关键词预匹配  
`preMatchKeyword()` 对正文做大小写无关的包含匹配，输出 `matched/matchedTerms`，作为 AI 判断提示的一部分，见 [server/src/services/ai.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/ai.ts:105)。

3. 真假识别 + 相关性分析  
`buildAnalysisPrompt()` 要求模型输出 JSON，包括 `isReal`、`relevance`、`relevanceReason`、`keywordMentioned`、`importance`、`summary`，并明确“未直接提及关键词要严格审核”，见 [server/src/services/ai.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/ai.ts:118)。

4. 过滤与保存  
`runHotspotCheck()` 对每条结果执行 `analyzeContent()`，然后按规则过滤：`isReal=false` 丢弃，`relevance < 50` 丢弃，未直接提及且 `relevance < 65` 丢弃，见 [server/src/jobs/hotspotChecker.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/jobs/hotspotChecker.ts:150)。通过后写入 `Hotspot`，包括 AI 摘要、相关性理由、重要程度、互动指标和作者信息，见 [server/src/jobs/hotspotChecker.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/jobs/hotspotChecker.ts:173)。

没有 OpenRouter key 时，代码会降级为基于预匹配的保守默认分数，见 [server/src/services/ai.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/ai.ts:155)。

**4. WebSocket 实时推送机制**
服务端 Socket.io 使用关键词房间模型。客户端连接后可发 `subscribe`，服务端把 socket 加入 `keyword:${kw}` 房间，见 [server/src/index.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/index.ts:51)。

当发现新热点：

- 向具体关键词房间推 `hotspot:new`。
- 向所有客户端广播 `notification`。

代码在 [server/src/jobs/hotspotChecker.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/jobs/hotspotChecker.ts:222)。

前端 Socket 单例在 [client/src/services/socket.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/client/src/services/socket.ts:5)，连接到 `window.location.origin`，支持 websocket 和 polling。`App` 加载关键词后自动订阅激活关键词，见 [client/src/App.tsx](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/client/src/App.tsx:102)。收到 `hotspot:new` 后前端把新热点插到列表头部、弹 toast、重新拉数据，见 [client/src/App.tsx](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/client/src/App.tsx:123)。

**5. 邮件通知系统**
邮件使用 Nodemailer。`getTransporter()` 从 `SMTP_HOST/SMTP_USER/SMTP_PASS/SMTP_PORT/SMTP_SECURE` 创建并缓存 transporter，配置缺失时直接禁用，见 [server/src/services/email.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/email.ts:18)。

邮件触发策略很克制：只有 `importance` 为 `high` 或 `urgent` 的热点才调用 `sendHotspotEmail()`，见 [server/src/jobs/hotspotChecker.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/jobs/hotspotChecker.ts:232)。邮件模板包含标题、重要性 badge、摘要、来源、相关性、关键词和原文链接，见 [server/src/services/email.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/email.ts:55)。另外还预留了日报 `sendDigestEmail()`，但当前定时任务没有调用，见 [server/src/services/email.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/services/email.ts:115)。

**6. 关键词监控配置和激活/暂停管理**
关键词模型里 `text` 唯一，`isActive` 默认 `true`，见 [server/prisma/schema.prisma](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/prisma/schema.prisma:13)。后端关键词路由支持：

- 创建关键词：校验非空，重复时返回 409，见 [server/src/routes/keywords.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/routes/keywords.ts:48)。
- 更新关键词：可改 `text/category/isActive`，见 [server/src/routes/keywords.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/routes/keywords.ts:74)。
- 激活/暂停切换：`PATCH /:id/toggle` 取反 `isActive`，见 [server/src/routes/keywords.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/routes/keywords.ts:115)。

监控任务只读取 `isActive: true` 的关键词，见 [server/src/jobs/hotspotChecker.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/jobs/hotspotChecker.ts:43)。前端关键词页用 toggle 开关控制状态，见 [client/src/App.tsx](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/client/src/App.tsx:173)。

**7. Agent Skills 技能包封装**
`skills/hot-monitor` 是一个独立的 Agent Skill，不依赖服务端和数据库。它把热点发现能力封装成脚本工作流：理解意图 → 执行多源搜索脚本 → 由 Agent 自己分析 → 输出报告，见 [skills/hot-monitor/SKILL.md](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/skills/hot-monitor/SKILL.md:28)。

技能包声明支持 Bing、Google、DuckDuckGo、HackerNews、Sogou、Bilibili、Weibo、Twitter，见 [skills/hot-monitor/SKILL.md](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/skills/hot-monitor/SKILL.md:3)。脚本分为：

- `search_web.py`：国际源。
- `search_china.py`：国内源。
- `search_twitter.py`：Twitter。
- `generate_report.py`：从 JSON 生成 Markdown 报告。

这和主应用的区别是：应用后端用 OpenRouter 自动分析并入库，Skill 则是“无服务、无数据库”的一次性检索/报告工具。

**8. 前端筛选、排序、展示设计**
前端的数据加载在 `loadData()`：并行拉关键词、热点分页、统计、通知，然后订阅激活关键词，见 [client/src/App.tsx](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/client/src/App.tsx:72)。

筛选排序有两套使用方式：

- 仪表盘热点流：筛选参数传给 `/api/hotspots`，由后端分页和排序，见 [client/src/App.tsx](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/client/src/App.tsx:76)。
- 手动搜索结果：前端本地 `useMemo` 过滤和排序，见 [client/src/App.tsx](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/client/src/App.tsx:253)。

筛选组件 `FilterSortBar` 支持来源、重要程度、关键词、时间范围、真实性，以及排序字段 `createdAt/publishedAt/importance/relevance/hot`，见 [client/src/components/FilterSortBar.tsx](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/client/src/components/FilterSortBar.tsx:36)。后端热点列表对应支持 `source/importance/keywordId/isReal/timeRange/timeFrom/timeTo/sortBy/sortOrder`，见 [server/src/routes/hotspots.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/routes/hotspots.ts:10)。

热点卡片展示很信息密集：重要性、来源、关键词、真实性、是否直接提及、热度分、AI 摘要、作者、点赞/转发/评论/浏览/弹幕、发布时间、抓取时间，并支持展开 AI 分析理由和原始内容，见 [client/src/App.tsx](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/client/src/App.tsx:587)。热度分前端用互动指标加权并 log 压缩到 0-100，见 [client/src/App.tsx](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/client/src/App.tsx:25)。

后端也有共享排序工具，`importance` 和 `hot` 因为 Prisma 不支持自定义排序而采用内存排序再分页，见 [server/src/routes/hotspots.ts](/home/suuuu/develop/intelligence-system/archive/yupi-hot-monitor/server/src/routes/hotspots.ts:69)。

**关键结论**
这个项目的架构核心是“关键词驱动的多源采集 + AI 精筛 + 实时通知”。优点是接口清晰、数据模型统一、抓取源容错好、AI 判断结果可解释；主要注意点是：虽然类型和 Skill 层支持 8 个来源，但主定时任务当前只启用了 6 个常规来源，Google/DuckDuckGo 处于实现但未接入主轮询的状态。