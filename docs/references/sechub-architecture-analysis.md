基于 [api-routes.txt](/tmp/sechub-data/api-routes.txt:1)，SecHub 更像一个“GitHub 行为情报站”而不是普通资讯站：WordPress 只承担 `/wp-json/` 的 API 交付，核心能力是把被监控的 `tracker_user` 的 `star/follow/fork` 行为，沉淀成事件流、排行榜、日报和画像，再用 `deepseek-v4-flash` 做中文富化。

1. API 路由设计  
- `timeline`：底层事实流，按事件时间输出单条行为记录，是所有上层视图的原始来源。  
- `digest`：精选流，应该是从 `timeline` 里按 `insight_score`、时效性、主题价值筛出来的高价值项，对应前端“精选”。  
- `daily-reports`：按 `report_date` 聚合的一天一报，是时间维度的叙事层，不是单事件层。  
- `hot-repos`：仓库维度的热点榜，按多个 `tracker_user` 对同一仓库的关注/转化行为聚合。  
- `hot-users`：文件没给 schema，但从命名看应是用户维度热点榜，结构大概率和 `hot-repos` 同构，只是实体换成 GitHub 用户。  
- `user-profiles`：用户画像集合，是从行为历史反推兴趣结构的结果。  
- `available-months`、`languages`、`profile-tags`：都是辅助维度接口，给前端筛选和归档用。  
- `repo-trend`、`repo-detail`、`user-profile-detail`：都是下钻详情，不是主信息流。

2. 数据模型的字段意图  
- `timeline item`：宽表式事件模型。  
  - 事实层：`id`、`event_type`、`event_time`、`tracker_user_id`。  
  - 仓库快照：`repo_full_name`、`repo_description`、`repo_language`、`repo_stars_count`、`repo_url`。  
  - 用户快照：`github_username`、`avatar_url`；若是 follow 事件，还会有 `followed_username`、`followed_user_id`、`followed_avatar_url`、`followed_bio`。  
  - AI 层：`summary_zh`、`recommendation_reason`、`insight_tags`、`insight_score`、`insight_model`、`insight_generated_at`。  
  这说明它不是纯日志，而是“事件事实 + 对象快照 + AI 注释”三合一。  
- `daily report`：时间桶文档。`report_date` 是主键，`title_zh` 和 `summary_zh` 是叙事输出，`highlights[]` 和 `stats[]` 是结构化支撑，`model`/`generated_at` 负责可追溯。  
- `hot-repos`：仓库聚合文档。`stars_count` 更像聚合排序字段，`tracker_count` 是触发该热点的监控用户数，`trackers[]` 则是证据列表，用来解释“为什么它热”。  
- `user-profile`：人设文档。`profile_text` 是中文画像摘要，`tags` 是主题标签集合，`star_count` 是证据量，`generated_at` 是版本时间。

3. GitHub 行为追踪的核心机制  
- `tracker_user` 更像被系统持续监控的一组 GitHub 账号，而不是普通站内用户。`tracker_user_id` 是内部主键，`github_username`/`avatar_url` 是展示字段。  
- `event_type` 至少包含 `star`、`follow`、`fork`。它不仅决定展示图标，还决定字段分支：  
  - `star/fork` 走仓库路径，进入 `hot-repos`、`digest`、`user-profiles`。  
  - `follow` 走用户路径，进入 `hot-users` 和“关注用户”视图。  
- 热门项目/用户的本质不是 GitHub 全站榜单，而是“被一组跟踪账号共同关注的对象”。这是一种 cohort-based 热度，而不是绝对热度。  
- `hot-repos` 里的 `trackers[]` 很关键，它把“结论”变成“证据可见”，便于解释和信任建立。

4. AI 分析层  
按你指定的 `deepseek-v4-flash`，这套系统更像“批处理摘要器 + 标签抽取器 + 评分器”，不是对话机器人。  
- `summary_zh`：把结构化事实压成短中文摘要，回答“它是什么”。  
- `recommendation_reason`：说明“为什么值得看”。  
- `insight_tags`：从 repo 描述、语言、事件类型、用户 bio 中抽取主题标签。  
- `insight_score`：用于排序和阈值筛选，通常是规则分数 + 模型判断的混合值。  
- `insight_model`、`insight_generated_at`：保留模型版本和生成时间，方便回溯和重算。  
更合理的做法是：先规则聚合，再让 `deepseek-v4-flash` 输出受约束的 JSON，最后落库成可缓存的业务字段。

5. 用户画像生成  
用户画像大概率主要从 `star` 行为推导。  
- 先收集某个 `tracker_user` 在一个时间窗内 star 的仓库。  
- 再把仓库的 `language`、`description`、主题关键词做归一化和聚类。  
- `tags` 用于结构化表达兴趣方向，适合过滤和推荐。  
- `profile_text` 则是面向中文读者的人设总结，比如“偏好 AI infra / 安全工具 / Rust 基础设施”。  
- `star_count` 不是装饰字段，而是画像可信度和覆盖度的证据量。  
这说明画像不是社交标签，而是“行为兴趣画像”。

6. 日报生成  
- `report_date` 是核心分桶维度，说明日报是按天聚合的。  
- `title_zh` 应该是日报的主题标题，偏编辑化；`summary_zh` 是当天重点概览。  
- `highlights[]` 负责放最重要的项目/用户/事件，`stats[]` 负责放统计维度，比如事件数、热门语言、主题分布等。  
- `is_full` 很可能区分“完整版日报”和“简版摘要”。  
整体上，日报是 `timeline` 的日级叙事重写，不是简单列表。

7. 前端 6 个 tab 的数据流  
可以把它们理解成同一事件图谱的 6 个投影：  
- 精选：`digest`，score-driven 的高价值信息流。  
- 日报：`daily-reports`，date-driven 的日级归档。  
- 关注用户：大概率是 `timeline` 里 `follow` 事件的切片。  
- 热门项目：`hot-repos`，repo-centric 排行。  
- 热门用户：`hot-users`，user-centric 排行。  
- 用户画像：`user-profiles`，person-centric 兴趣剖面。  
这 6 个 tab 不是 6 套数据，而是 6 种视角。`available-months`、`languages`、`profile-tags` 是这些视角的筛选器；`repo-detail`、`repo-trend`、`user-profile-detail` 是下钻页。

8. 对你们情报系统的借鉴  
最值得直接复用的是这 4 个模式：  
- 事件事实层和派生视图层分离：先存统一事件，再产出精选、榜单、日报、画像。  
- 全量快照字段：actor、target、repo metadata 都要在事件写入时固化，避免历史漂移。  
- AI 产物持久化：`summary_zh`、`reason`、`tags`、`score` 不要请求时实时生成。  
- 结果可解释：给榜单附 `trackers[]`，给画像附 `star_count`，给 AI 字段附 `model/generated_at`。  

一句话总结：SecHub 的结构是“行为采集 -> 事件标准化 -> LLM 富化 -> 物化视图发布 -> 前端多视角消费”。这套模型很适合直接迁移到你们的情报系统里。