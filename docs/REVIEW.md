# Intelligence System — 架构评审记录

> 版本: v0.3 | 更新: 2026-05-26
> 状态: **历史评审记录，当前实现以 `.spec/` 为准**

---

## 已关闭的决策（全部已落入 .spec/）

| ID | 问题 | 决定 |
|----|------|------|
| C1 | 初始源优先级 | 安全 6 源 + AI 4 源，保守起步 |
| C2 | 微信公众号 | 不做 |
| A1 | Stage 2 阈值 | **75** |
| A2 | 分类体系 | 慢慢增多，security + ai 起步 |
| A3 | 实体类型 | 推到 Phase 2，Phase 1 不做实体图谱 |
| O1 | 日报时间 | 00:00 北京开始爬，爬完即推，不卡固定时间 |
| O2 | 实时推送阈值 | 慢慢找优质源，Phase 2 再做实时推送 |
| X1 | 推送渠道 | Hexo post 作为博客内容 (Phase 1) + OSS 备份 + 飞书推送 (Phase 2) |
| X2 | MCP | Phase 2+，Phase 1 不做 |
| D1 | 搜索引擎 | MySQL FULLTEXT + ngram，怎么好用怎么来 |
| D2 | 数据保留 | <10 立删 / <30 五天 / <50 十天 / <75 三十天 / ≥75 永久 |
| M1 | AI 成本 | NVIDIA 优先，但不假设无限免费；按实际限流和可用额度实现 |
| M2 | 模型 fallback | NVIDIA 为主，Sub2API 备用；不设过小输出上限，但使用 provider-compatible cap |
| P1 | Redis | 装到 114（已部署） |
| P2 | API 范围 | 内部，不对外 |
| T1 | 时间表 | 慢慢来 |
| T2 | 初始 RSS | 从参考项目提取，从零开始 |

## 架构审查修正（2026-05-26）

以下架构债已修复并更新到 .spec/ 文件：

| 问题 | 修复 |
|------|------|
| channels 表是伪抽象 | 砍掉，domain 作为 enum 直接放 sources/items |
| item_analysis 分离导致 JOIN 税 | 合并进 items 表 |
| source_fetches 过度设计 | 并入 runs.stats_json |
| retention_class 冗余 | 删掉，expires_at 够了 |
| Docker 容器访问不到宿主机 SSH tunnel | 使用 network_mode: host |
| 缺少并发运行保护 | 加 run lock，只允许一个 run 同时运行 |
| 多处 draft/TBD 但已确认 | 全部更新为 confirmed 状态 |
| Review Gate 太重 | 简化为：URL 能跑通 + 内容有信号 + dedup key 明确 = approved |
| 缺少 prompt 版本管理 | 定义 s1_v1/s2_v1 语义标签 |
| 跨源去重丢信息 | 加 also_seen_in JSON 字段，记录重复来源 |

---

## 剩余开放问题（需要你回答）

### Q1: 博客怎么读日报？（已收敛为 Phase 1 默认）

Phase 1 默认直接写 Hexo post 到 `/opt/blog/source/_posts/`，同时把同一份 Markdown 备份到 OSS (`suuuuzsk/intelligence/digests/2026-05-26/security.md`)。

待验证项变成：38 上的 worker 是否有权限写目标博客目录。

- 备选 A: OSS HTTP URL。
- 备选 B: API proxy。
- 备选 C: 已废弃。Phase 1 使用 worker 直接写 Hexo path，并通过 oss2 SDK 上传 OSS 备份。

### Q2: X/Twitter 爬取你有想过具体方案吗？

你提到想爬 X 上的安全大牛，可以提供账号。在我调研方案之前想确认：

- 你有 X/Twitter API（付费 Basic/Pro tier）吗？还是只能免费方案？
- 你能接受用 Nitter 实例（公共实例不稳定，自建需要维护）吗？
- 还是想要 RSSHub 这种桥接方案？
- 账号列表大概有多少人？

这个不影响 Phase 1，但想提前了解思路。

---

## 参考项目分析（保留，不再是决策输入）

> 以下为之前的 9 个参考项目分析，作为历史记录保留。
> 所有设计决策已迁移到 `.spec/` 目录，参考项目分析不再作为直接的设计依据。
> 需要回顾参考项目时看 `docs/references/` 目录。
