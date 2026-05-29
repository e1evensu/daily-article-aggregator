以下分析基于 [skill-spec.txt](/tmp/aihot-data/skill-spec.txt:1)；这份文件是技术规格摘要，不是完整实现代码，所以我会区分“规格明确写出”和“从规格可推导出的架构模式”。

**总体架构**

aihot-skill 的核心是“REST API + Agent Skill”双层架构：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:3) 明确写到类型是 `REST API + Agent Skill integration`，公共 API 基地址是 `https://aihot.virxact.com/api/public/`。这意味着它不是一个只服务网页的内容站，而是把 AI 热点情报先产品化为 API，再通过 Agent Skill 封装为 Claude Code、Cursor 等工具可调用的能力。

整体可以理解为四层：

1. 数据层：AI 新闻、模型、产品、论文、技巧等 item。
2. API 层：提供日报、精选、全量、历史归档、分页、搜索、分类过滤。
3. Skill 路由层：把用户自然语言请求映射到对应 REST 端点。
4. Briefing 渲染层：把 API 返回的数据组织成 Markdown 简报。

---

**1. API-first 设计：REST 端点与路由逻辑**

规格中最关键的一点是路由逻辑：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:35)：

- `Wide questions → selected items with time windows`
- `Explicit "日报" → dedicated daily endpoints`
- `"complete" requests → full unfiltered pool`

这说明 aihot-skill 的 Skill 层不是简单透传用户请求，而是有一个“意图路由器”。

对于宽泛问题，比如“最近 AI 模型有什么重要进展”“这周有什么 AI 产品更新”，系统不会直接查全量池，而是优先访问“精选 + 时间窗口”的接口。原因很明确：宽泛问题的目标是高信噪比，不是穷尽。它会把请求转换成类似：

```text
category=models/products/industry
time_window=recent N days
source=selected
```

也就是以“精选”为默认召回源，用时间窗口限制范围，再按分类或关键词收窄。

对于明确包含“日报”的请求，比如“给我今天的 AI 日报”“查看 5 月 20 日日报”，系统会走 dedicated daily endpoint，而不是重新搜索 item 拼一份。这是很重要的设计：日报是一个已经策展过的 briefing artifact，不只是 item 列表。它应该有固定日期、固定结构、固定排序和编辑选择。

对于用户明确要求 `complete`、全量、完整列表、不要筛选时，系统才进入 full unfiltered pool。这个路径适合研究、审计、二次分析、构建外部知识库，但默认不用于普通问答，因为噪声和分页成本更高。

这个 API-first 模式的好处是：Agent 只是调用者之一。网页、CLI、自动化任务、内部数据管道都可以复用同一组 REST 端点，而不是把业务逻辑写死在某个聊天工具里。

---

**2. 内容分类体系：5 个 domain 的组织方式**

规格定义了 5 个一级领域：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:14)：

1. Models，模型
2. Products，产品
3. Industry news，行业
4. Papers，论文
5. Tips，技巧

这是一个非常适合 AI 情报系统的扁平一级分类法。它不是按来源分类，也不是按公司分类，而是按“用户消费情报的任务场景”分类。

模型类关注基础模型、开源模型、能力更新、评测结果、API 模型发布。  
产品类关注应用、平台、工具、功能上线、商业化产品。  
行业类关注融资、公司动态、政策、竞争格局、市场事件。  
论文类关注研究成果、方法创新、benchmark、实验结论。  
技巧类关注 prompt、工作流、工具用法、开发经验、实践方案。

规格还写到每条 item 有 `Categorical tags`：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:32)。这意味着分类体系大概率是“一级 domain + 多标签”的组合。一级 domain 用于主导航和 API 过滤，tags 用于更细粒度的主题检索。例如一条 OpenAI 新模型发布可以属于 `Models`，同时带有 `OpenAI`、`reasoning`、`API` 等标签。

这种设计的优点是清晰、稳定、低维护成本。一级分类不要太多，否则 Agent 路由会变复杂；细节交给 tags 和 keyword search 处理。

---

**3. 日报生成机制：08:00 UTC、精选 vs 全量**

规格明确写到日报每日 `08:00 UTC` 生成：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:9)。换算成北京时间是每日 `16:00`，因为北京时区是 UTC+8。

这带来一个产品语义上的细节：如果用户在北京时间上午问“今天的日报”，系统可能拿到的仍是前一版或尚未生成的当日版。Skill 层应该明确处理日期边界：API 数据使用 ISO 8601 UTC 时间戳：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:31)，但输出需要转换为北京时间：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:42)。

日报、精选、全量三者应理解为不同的数据产品：

- 日报：每日固定生成的结构化简报，强调可读性、稳定排序、跨分类覆盖。
- 精选：编辑挑选的 item，可以跨日期、跨分类，用于回答宽泛问题。
- 全量：完整未过滤池，适合 exhaustive 查询和外部处理。

精选 vs 全量的筛选标准虽然规格没有展开，但从字段和内容类型可以推导：

- 精选看重重要性、代表性、新颖性、可信来源和跨领域覆盖。
- 全量保留所有规范化 item，只要求满足入库标准。
- 日报可能从精选中抽取，也可能在每日窗口内结合全量池重新策展。

因此，日报生成机制可以抽象为：

```text
抓取/入库 → 标准化标题与摘要 → 分类与打标签 → 编辑/规则精选 → 08:00 UTC 生成日报 → 历史归档
```

其中“历史归档”也是规格明确列出的内容类型：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:12)，说明日报不是临时响应，而是可按日期访问的持久产物。

---

**4. Agent Skill 集成模式**

规格把它定义为 Agent Skill integration：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:3)。这类 Skill 的本质是给 Claude Code、Cursor 等 Agent 工具提供一个“可调用的信息能力”。

它通常包含三部分：

1. 什么时候调用：用户询问 AI 热点、日报、模型进展、论文、产品动态时触发。
2. 调什么端点：根据意图选择 daily、selected 或 complete。
3. 怎么输出：把返回数据整理成符合规范的 Markdown briefing。

这里的设计重点不是让 Agent 自己上网搜索，而是让 Agent 调用一个稳定、专用、限速明确的情报 API。规格写了 `600 req/min per IP` 和需要 browser User-Agent header：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:5)。这说明它把调用行为当成正式 API 消费来管理，而不是非结构化爬取。

这种模式对 Agent 很友好：Agent 不需要判断哪些来源可信、不需要去网页抽取正文、不需要自己做分类，只需要完成请求路由、参数构造、分页、结果压缩和格式化。

---

**5. 分页和搜索设计**

规格列出两个关键 API 能力：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:21)：

- Server-side keyword matching，匹配 titles + summaries
- Pagination via opaque cursor tokens

搜索放在服务端做，而不是客户端拉全量再过滤。这是正确的 API 设计，因为情报库会持续增长，全量拉取成本高，也会让 Agent 浪费上下文窗口。

关键词匹配范围是标题和摘要：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:24)。这说明搜索偏轻量，不一定是完整语义检索或全文检索。它适合问题如“OpenAI 最近有什么”“找一下 Gemini 相关更新”“最近有什么 agent 论文”。

分页采用 opaque cursor tokens：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:25)。这比 `page=2` 更适合动态内容流，因为 cursor 可以封装排序位置、时间边界、查询条件和内部 ID。客户端不需要知道 cursor 的结构，只需要把 `next_cursor` 原样传回。

这对 Agent 特别重要：Agent 可以根据用户需求决定是否继续翻页。普通简报只取第一页；用户要求“继续”“更完整”“全部列出”时才使用 cursor 继续请求。

---

**6. 输出格式：Markdown briefing 规范**

规格要求输出为 Markdown briefing：[skill-spec.txt](/tmp/aihot-data/skill-spec.txt:40)，并包含三项格式要求：

- 北京时区转换
- 相对时间表达
- 跨 section 的全局编号

这说明输出层不是简单 JSON dump，而是面向人读的情报简报。

一个合理的 Markdown briefing 结构应类似：

```markdown
# AI 热点简报

生成时间：2026-05-26 16:00 北京时间
范围：过去 24 小时 / 过去 7 天

## 模型
1. 标题
   来源：OpenAI Blog
   时间：今天 10:30，北京时间
   摘要：...

## 产品
2. 标题
   来源：...
   时间：2 天前
   摘要：...
```

“全局编号 across sections”很关键。它意味着编号不在每个分类里重新从 1 开始，而是整份简报连续编号。这样用户可以直接说“展开第 7 条”“第 12 条和第 15 条有什么关系”，Agent 可以稳定引用。

时区转换也很重要。API 内部使用 UTC ISO 8601，输出给中文用户时转换为北京时间，并同时支持“今天”“昨天”“3 小时前”这样的相对时间。这里最好保留绝对时间，避免相对时间在异步对话里失真。

---

**7. 对我们情报系统的借鉴**

可以复用的模式主要有四类。

第一，API 设计。  
把情报能力先设计成 API，而不是先做聊天界面。建议也采用 `daily / selected / complete / archives` 这样的资源分层：日报负责固定产物，精选负责高信噪比问答，全量负责研究型查询，历史归档负责可追溯性。

第二，分类体系。  
采用少量稳定一级 domain，再用 tags 承载细节。一级分类不要被热点牵着走，否则长期维护困难。对于 AI 情报，`模型 / 产品 / 行业 / 论文 / 技巧` 是一个可直接复用的骨架。

第三，Agent 集成。  
Agent Skill 不应该直接负责抓取和判断真伪，而应该作为 API 编排层：识别意图、选择端点、构造参数、处理分页、渲染简报。这样 Claude Code、Cursor、内部 bot、自动日报任务都能复用同一后端。

第四，简报生成。  
把“日报”当成持久化内容产品，而不是每次临时生成。固定生成时间、固定 schema、固定输出结构、支持历史归档。输出上使用 Markdown、全局编号、时区转换、相对时间和来源归因，可以显著提高可读性和后续追问能力。

最值得直接借鉴的是这个路由原则：宽泛问题默认走精选，明确日报走日报端点，明确全量才走 complete pool。这个设计能同时兼顾体验、成本和可控性。