**总体判断**

`ljg-skills` 不是一个简单 prompt 集，而是一个 Claude Code Skill 插件仓库。核心架构是：

`插件清单 -> skills 目录 -> 单个 skill 包 -> SKILL.md + references/assets/scripts/workflows`

入口在 [.claude-plugin/plugin.json](/home/suuuu/develop/intelligence-system/archive/ljg-skills/.claude-plugin/plugin.json:1)，其中 `"skills": "./skills"` 明确告诉安装器技能目录在 `skills/` 下；[README.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/README.md:7) 则把安装方式定义为 `npx skills add lijigang/ljg-skills -g --all`。

**1. 目录结构**

仓库分四层：

1. 根层：`README.md`、`CLAUDE.md`、`.claude-plugin/`、`scripts/`
2. 插件清单层：`.claude-plugin/plugin.json` 和 `marketplace.json`
3. 技能层：`skills/ljg-*/SKILL.md`
4. 技能资源层：`references/`、`assets/`、`scripts/`、`Workflows/`、`Tools/`

`.gitignore` 采用“默认忽略所有，再显式放行”的发布模型：[.gitignore](/home/suuuu/develop/intelligence-system/archive/ljg-skills/.gitignore:1) 先 `*` 忽略全部，再放行 `README.md`、`.claude-plugin/**`、`scripts/**`、`skills/**`。这说明仓库被当成一个可分发制品，而不是普通项目目录。

单个 skill 的基本形态是：

```text
skills/ljg-card/
  SKILL.md
  references/
  assets/
  package.json
```

复杂技能会带执行资产。例如 `ljg-card` 有 HTML 模板、截图脚本和 Playwright 依赖：[skills/ljg-card/package.json](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-card/package.json:1) 只依赖 `playwright`；截图入口是 [skills/ljg-card/assets/capture.js](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-card/assets/capture.js:14)，用法是 `node capture.js <html> <png> [width] [height] [fullpage]`。

有一点架构漂移：`CLAUDE.md` 里示例写的是根目录 `ljg-*`：[CLAUDE.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/CLAUDE.md:11)，但实际仓库和 `plugin.json` 都是 `skills/ljg-*`。根文档中的历史安装命令 `cp -r ljg-* ~/.claude/skills/` 也已不符合当前目录结构：[CLAUDE.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/CLAUDE.md:65)。

**2. Skill 功能定位**

可以按五类理解：

| 类别 | Skill | 定位 |
|---|---|---|
| 认知原子 | `ljg-plain` | 把内容改写到“聪明的 12 岁孩子能懂”，强调 grok 和口语化：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-plain/SKILL.md:8) |
| 认知原子 | `ljg-think` | 纵向深钻观点，追到不可再分的本质：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-think/SKILL.md:18) |
| 认知原子 | `ljg-rank` | 给领域“降秩”，找不可再少的生成器：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-rank/SKILL.md:11) |
| 认知原子 | `ljg-learn` | 八个方向解剖概念，最后压成顿悟：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-learn/SKILL.md:22) |
| 认知原子 | `ljg-word` | 单词词源、核心意象、语义掌握：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-word/SKILL.md:17) |
| 写作 | `ljg-writes` | 针对一个观点写 1000-1500 字批判性文章：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-writes/SKILL.md:8) |
| 阅读研究 | `ljg-paper` | 论文讲解，把论文讲成七拍故事：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-paper/SKILL.md:25) |
| 阅读研究 | `ljg-paper-river` | 论文倒读法，递归追前序论文和后续进展：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-paper-river/SKILL.md:12) |
| 阅读研究 | `ljg-book` | 拆书，抓核心问题、假设、框架、结论、精神内核：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-book/SKILL.md:17) |
| 阅读研究 | `ljg-read` | 伴读，翻译、结构标注、追问和旁逸：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-read/SKILL.md:33) |
| 阅读研究 | `ljg-qa` | 把文章/书/论文抽成有方向的 Q-A 链：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-qa/SKILL.md:24) |
| 判断分析 | `ljg-invest` | 投资分析，判断项目是否是“秩序创造机器”：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-invest/SKILL.md:41) |
| 对话模拟 | `ljg-roundtable` | 多人物圆桌辩证讨论：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-roundtable/SKILL.md:22) |
| 关系诊断 | `ljg-relationship` | 关系问题的结构诊断和精神分析式提问：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-relationship/SKILL.md:28) |
| 输出铸造 | `ljg-card` | 内容转 PNG，可长图、信息图、漫画、白板、大字等：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-card/SKILL.md:12) |
| 输出铸造 | `ljg-present` | 把 org/markdown outline 1:1 渲染成演讲 HTML：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-present/SKILL.md:20) |
| 工作流 | `ljg-paper-flow` | `ljg-paper -> ljg-card`，读论文后铸卡：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-paper-flow/SKILL.md:31) |
| 工作流 | `ljg-word-flow` | `ljg-word -> ljg-card -i`，解词后做信息图：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-word-flow/SKILL.md:31) |
| 工作流 | `ljg-travel` | 城市文化旅行研究，生成 org 文档和便携卡片：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-travel/SKILL.md:91) |
| 运维 | `ljg-skill-map` | 扫描已安装技能并渲染 ASCII 技能地图：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-skill-map/SKILL.md:14) |
| 运维 | `ljg-push` | 把本地 `~/.claude/skills/ljg-*` 同步到 GitHub 双分支：[SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-push/SKILL.md:21) |

**3. SKILL.md 规范**

`SKILL.md` 的共同结构是 YAML frontmatter + 执行说明。`CLAUDE.md` 给出的标准字段是 `name`、`description`、`user_invocable`、`version`：[CLAUDE.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/CLAUDE.md:22)。

典型 frontmatter：

```yaml
---
name: ljg-card
description: "Content caster..."
user_invocable: true
version: "2.3.0"
---
```

见 [skills/ljg-card/SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-card/SKILL.md:1)。

好的 `description` 不只是说明功能，还写触发语和排除条件。例如 `ljg-book` 明确写 `Use when...`，并排除“章节摘要、论文、单一观点深钻、领域降秩”等误触场景：[skills/ljg-book/SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-book/SKILL.md:1)。

正文通常包含：

- 身份/边界：例如 `ljg-qa` 先写“你不是 FAQ 生成器”：[skills/ljg-qa/SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-qa/SKILL.md:13)
- 输入获取：URL 用 WebFetch，PDF/本地文件用 Read，文本直接处理；`ljg-paper` 明确列出这些路径：[skills/ljg-paper/SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-paper/SKILL.md:217)
- 输出格式：大量技能默认写入 `~/Documents/notes/`，使用 Denote 命名
- 红线/验收：例如 `ljg-paper` 最后有完整验收清单：[skills/ljg-paper/SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-paper/SKILL.md:351)
- references 分离：复杂规则不堆在主文件里，放到 `references/` 或 `Workflows/`

一个重要规范是“模板权威性”。`ljg-paper` 明确说输出结构依据 `references/template.org`，禁止参考旧 notes 文件：[skills/ljg-paper/SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-paper/SKILL.md:76)。模板本身在 [skills/ljg-paper/references/template.org](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-paper/references/template.org:1)，使用 `#+title`、`#+filetags`、`#+identifier` 等 org 元数据。

**4. `npx skills add` 安装机制**

仓库没有包含 `skills CLI` 源码，所以只能基于 README 和 manifest 分析其工作方式。

README 给出的安装命令是：

```bash
npx skills add lijigang/ljg-skills -g --all
npx skills add lijigang/ljg-skills#md -g --all
npx skills add lijigang/ljg-skills -g --skill ljg-card
```

见 [README.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/README.md:7)。

参数语义在 README 中写得很清楚：

- `-g`：安装到 `~/.claude/skills/`
- 不加 `-g`：安装到当前项目 `.claude/skills/`
- `--skill <name>`：选择单个技能，可重复
- `--all`：安装全部技能
- `#md`：从 `md` branch 安装 Markdown 版本
- `-l`：只列出可用技能

见 [README.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/README.md:29)。

推断安装流程是：

1. CLI 解析 `lijigang/ljg-skills[#branch]`
2. 拉取 GitHub 仓库对应分支
3. 读取 `.claude-plugin/plugin.json`
4. 根据 `"skills": "./skills"` 找到技能目录
5. 按 `--all` 或 `--skill` 复制 skill 目录到目标位置
6. 不自动安装 skill 内部依赖

`ljg-card` 是依赖型技能，README 要求安装后手动执行：

```bash
cd ~/.claude/skills/ljg-card && npm install && npx playwright install chromium
```

见 [README.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/README.md:39)。根脚本 [scripts/install.sh](/home/suuuu/develop/intelligence-system/archive/ljg-skills/scripts/install.sh:8) 也只处理 `ljg-card` 的 npm/Playwright 依赖。

**5. Org-mode vs Markdown**

这个仓库的默认源格式是 org-mode，Markdown 是另一个发布分支。

README 定义：

| Branch | 格式 | 场景 |
|---|---|---|
| `master` | Org-mode | Emacs / Denote |
| `md` | Markdown | Obsidian / VSCode / Notion |

见 [README.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/README.md:91)。

`ljg-push` 对两者差异写得最明确：[skills/ljg-push/SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-push/SKILL.md:21)

- org-mode：`.org`、`*bold*`、`#+title:`
- Markdown：`.md`、`**bold**`、YAML frontmatter

自动转换不是完整 AST 转换，而是字符串替换。`Push.sh` 的 `mdize_skill()` 只替换 `__paper.org -> __paper.md`、`template.org -> template.md`、`org-mode -> markdown` 等：[skills/ljg-push/Tools/Push.sh](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-push/Tools/Push.sh:101)。它明确不处理 `*bold* -> **bold**`、org 文件头到 YAML frontmatter、真实文件重命名：[skills/ljg-push/SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-push/SKILL.md:63)。

选择建议：

- 如果知识库是 Emacs/Denote，选 org-mode。它的文件头、tags、identifier 和 `~/Documents/notes/` 约定已经很成熟。
- 如果要给团队、Web、Obsidian、VSCode、Notion 或 GitHub 阅读，选 Markdown。
- 如果要做长期可维护的多格式发布，不建议长期靠 sed 字符串替换。更稳的是定义一个中间结构或模板层，再分别渲染 org/md。

**6. 对情报系统 Agent Skill 的借鉴**

最值得借鉴的是“技能包”思想：一个 Agent 能力不只是 prompt，而是：

```text
SKILL.md        # 触发、边界、流程、验收
references/    # 方法论、模板、评分标准
assets/        # HTML、图片、样式、可视化模板
scripts/       # 可执行工具
Workflows/     # 多技能流程编排
```

对情报系统尤其有用的设计原则：

1. 把能力拆成“原子 skill + flow skill”。例如原子 skill 可以是 `source-ingest`、`entity-extract`、`event-timeline`、`credibility-score`、`claim-verify`、`brief-write`；flow skill 可以是 `daily-intel-brief`、`company-monitor`、`risk-alert`。

2. `description` 必须写触发词和 NOT FOR。`ljg-book` 这种写法能减少误触，对情报 Agent 很关键：新闻摘要、威胁研判、投资情报、人物画像、舆情监控不能混用。

3. 每个输出都要有模板权威性。类似 `ljg-paper/references/template.org`，情报系统应有 `brief-template.md`、`source-card-template.md`、`risk-report-template.md`，强制字段包括：来源、时间、事实、推断、置信度、证据链、未证实点。

4. 红线要前置。情报类 skill 至少要有：不编造来源；事实和推断分离；过期信息必须标日期；所有关键判断给证据；低置信度明确标注；无法验证就写“未验证”。

5. 工作流要显式串并行。`ljg-paper-flow` 规定“每篇论文内部先 paper 后 card，多篇之间并行”：[skills/ljg-paper-flow/SKILL.md](/home/suuuu/develop/intelligence-system/archive/ljg-skills/skills/ljg-paper-flow/SKILL.md:59)。情报系统也应写清楚哪些步骤可并行、哪些必须串行，比如“先采集，再去重，再交叉验证，再生成判断”。

6. 运维也应 skill 化。`ljg-skill-map` 和 `ljg-push` 说明作者把“查看能力地图”和“发布同步”都做成技能。情报系统也可以有 `agent-map`、`source-health-check`、`taxonomy-lint`、`brief-publish`。

7. 多格式发布要谨慎。`ljg-push` 的双分支策略实用，但字符串转换有维护风险。情报系统如果要同时支持 Markdown、HTML、PDF、Notion，最好从一开始设计结构化中间层，而不是后期靠替换扩展名。

一句话总结：`ljg-skills` 的核心价值不在某个提示词写得好，而在它把 Agent 能力产品化了：可安装、可触发、可组合、可验收、可发布。情报系统 Agent Skill 应该沿用这个包结构，但把“审美红线”换成“事实红线、证据红线、时效红线”。