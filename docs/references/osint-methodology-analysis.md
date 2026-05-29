**总体架构**

Claude-OSINT 本质上不是一个完整扫描平台，而是“方法论 Skill + 作战资料 Skill + 少量脚本”的知识型架构。项目明确把两类心智拆开：`osint-methodology` 负责“how to think”，`offensive-osint` 负责“what to reach for”，见 [docs/architecture.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/docs/architecture.md:3)。README 的能力图也把前者映射到 Recon Pipeline、Asset Graph、Findings Rubric，后者映射到 Probe Wordlists、Secret Catalog、Read-Only Validators 等能力域，见 [README.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/README.md:182)。

它的工程形态是“结构化 tradecraft 作为系统提示词”，不是传统库。真正可执行的部分主要是 `secret_scan.py` 和 `h1_reference.py`，其中 `secret_scan.py` 已把 secret catalog 部分内化成 Python 规则表。

**1. 置信度框架**

核心原则是“Every assertion carries a confidence level”，定义在 [skills/osint-methodology/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/osint-methodology/SKILL.md:87)。

| 等级 | 含义 | 典型证据 |
|---|---|---|
| `TENTATIVE` | 间接证据，尚未验证 | dork snippet、推断邮箱模式、单一 passive subdomain |
| `FIRM` | 直接观察，但未交叉验证 | DNS 解析成功、Shodan banner、CT log |
| `CONFIRMED` | 多源佐证或直接验证 | live token、bucket listable、三源 subdomain 收敛 |

升级工作流定义在 [skills/osint-methodology/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/osint-methodology/SKILL.md:99)：

| 资产类型 | TENTATIVE → FIRM | FIRM → CONFIRMED |
|---|---|---|
| Subdomain | ≥2 passive sources 或 DNS resolves | 标准端口服务可访问，且返回 banner/cert |
| IP | ≥2 sources，例如 passive DNS、ASN、Shodan | TCP SYN-ACK 或 ICMP reply |
| WebApp | URL extracted but not hit | HTTP 返回 2xx/3xx/4xx 且 content-length > 0 |
| Email | name-pattern inferred 或 snippet-only | Hunter/IntelX/breach 收录，或 SMTP 250 且 abort at DATA |
| Bucket | permutation + HEAD 返回 200/301/403 | GET listing 成功 |
| Credential / secret | captured text 中 regex 命中 | 只读 validator 成功，记录 scope/account-ID |
| Person | 单源姓名 | 第二独立来源确认 |
| SSO tenant | OIDC discovery 返回 metadata | tenant GUID + domain 通过 MX/autodiscover/SP 反绑 |

这套体系的关键不是“打标签”，而是把“升级条件”显式化。默认姿态是“无法明确佐证就降级”，见 [skills/osint-methodology/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/osint-methodology/SKILL.md:112)。

**2. 资产图谱模型**

资产图谱纪律定义为：每个发现都必须是 typed asset，而不是 free-floating string，见 [skills/osint-methodology/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/osint-methodology/SKILL.md:245)。

实体 taxonomy：

| 类别 | 类型 |
|---|---|
| DNS / Network | `domain`, `subdomain`, `ip`, `netblock`, `asn` |
| Service | `port`, `service`, `certificate` |
| Identity | `email`, `person`, `credential` |
| Code / Config | `repo`, `secret` |
| Cloud / Storage | `bucket`, `firebase_project` |
| Web | `webapp`, `wayback_endpoint`, `api_endpoint`, `api_spec`, `graphql_schema` |
| Mobile | `mobile_app`, `deep_link`, `exported_component` |
| Phishing | `typosquat_domain` |
| SaaS | `postman_collection`, `postman_workspace`, `postman_api_key`, `stack_post`, `saas_public_surface` |

每个 asset 固定携带 `type`, `key`, `value`, `sources[]`, `confidence`, `first_seen`, `last_seen`, `attrs{}`，见 [skills/osint-methodology/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/osint-methodology/SKILL.md:263)。

关系 schema 在 [docs/architecture.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/docs/architecture.md:86) 的图里明确给出核心边：

| From | Edge | To |
|---|---|---|
| `domain` | `ALIAS_OF` / `RESOLVES_TO` | `subdomain` |
| `subdomain` | `RESOLVES_TO` | `ip` |
| `ip` | `IN_NETBLOCK` | `asn` |
| `subdomain` | `HOSTED_ON` | `asn` |
| `subdomain` | `EXPOSES` | `webapp` |
| `webapp` | `DOCUMENTED_BY` | `api_spec` |
| `webapp` | `CONTAINS_SECRET` | `secret` |
| `secret` | `BREACHED_FROM` | `breach` |
| `breach` | `CONTAINS` | `email` |
| `email` | `EMPLOYED_BY` | `person` |

注意：README/skill README 声称有“23 typed edges”，见 [skills/osint-methodology/README.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/osint-methodology/README.md:37)，但当前仓库没有把完整 23 条边以表格或 schema 文件显式展开。这是一个规范缺口。

**3. 五阶段侦察管线**

管线定义在 [skills/osint-methodology/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/osint-methodology/SKILL.md:202)：五个阶段顺序执行，阶段内模块可并发。

| 阶段 | 目标 | 典型模块 |
|---|---|---|
| 1 Seed Discovery | 建立初始边界 | WHOIS、ASN、DNS records、CT history |
| 2 Asset Expansion | 扩展攻击面 | subdomain enum、bucket permutation、typosquat、Wayback、mobile discovery、LinkedIn |
| 3 Enrichment | 给资产补上下文 | Shodan/naabu、TLS/JARM/favicon、WAF/CDN、security headers、GitHub dork、JS analysis、SSO/IdP、API discovery、secret sweep |
| 4 Exposure Analysis | 找可报告暴露 | nuclei always-on、TLS deep audit、breach × identity、`.git/config`, `.env`, `/actuator/env`, `/_cat/indices`, CVE × EPSS × KEV × POC |
| 5 Reporting | 风险固化为交付物 | risk scoring、asset graph export、client report、reproduction package、bug bounty submission |

优先级顺序不是“按工具跑一遍”，而是按信号密度排序：breaches → GitHub recon → nuclei misconfig → cloud buckets → ports → email OSINT → web tech/WAF/screenshots → Wayback → DNS/email security → certificates/TLS → ASN/reverse DNS → typosquats，见 [skills/osint-methodology/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/osint-methodology/SKILL.md:214)。

时间预算也被编码为 profiles：1-hour rapid、4-hour focused、1-day standard、1-week deep、ongoing weekly diff，见 [skills/osint-methodology/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/osint-methodology/SKILL.md:229)。

**4. Finding 输出 schema**

Finding schema 在 [skills/osint-methodology/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/osint-methodology/SKILL.md:116)：

```yaml
Finding:
  id:          <stable hash or UUID>
  module:      <technique that discovered it>
  asset_key:   <typed key, e.g. sub:api.example.com>
  category:    <e.g. SECRET_LEAK, OPEN_GRAPHQL_API, SSO_EXPOSURE>
  severity:    <info|low|medium|high|critical>
  confidence:  <tentative|firm|confirmed>
  title:       <one-line summary>
  description: <2-5 sentences>
  evidence:
    url:       <where found>
    timestamp: <UTC ISO8601>
    sha256:    <hash of any downloaded artifact>
    raw:       <truncated to 2 KiB>
  references:  [<CVE-ID, advisory URL, vendor doc>]
  remediation: <action the asset owner can take>
```

它的设计重点是 ingestion-friendly：`asset_key` 绑定资产图谱，`severity/confidence` 绑定评分系统，`evidence` 绑定可复核证据，`sha256` 和 UTC timestamp 支持证据链。

**5. 48 个 secret regex 与 9 个只读 validator**

文档 catalog 在 [skills/offensive-osint/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/offensive-osint/SKILL.md:1685)，表格列出 48 个 pattern。设计方式是五元组：`Name`, `Regex`, `Severity`, `Category`，并强调“most-specific patterns first”，避免 generic rule 抢先匹配。

覆盖面：

| 组 | 代表 |
|---|---|
| Base 29 | AWS、GCP、GitHub、Stripe、Slack、SendGrid/Mailgun、Twilio、Heroku、Firebase、JWT/Bearer/Basic Auth、private keys、generic API key |
| Modern 19 | Anthropic/OpenAI/HuggingFace、Cloudflare/DigitalOcean、npm/PyPI/Docker Hub、Atlassian/Linear、New Relic/DataDog/Sentry、ngrok、Discord/Telegram |

可执行实现是 [secret_scan.py](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/offensive-osint/scripts/secret_scan.py:28)：

```python
PATTERNS = [
    ("AWS_ACCESS_KEY", SEV_CRITICAL, "aws", r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("GH_PAT_CLASSIC", SEV_CRITICAL, "github", r"\bghp_[A-Za-z0-9]{36}\b"),
    ("OPENAI_PROJECT", SEV_CRITICAL, "ai_api", r"\bsk-proj-[A-Za-z0-9_\-]{40,}T3BlbkFJ[A-Za-z0-9_\-]{40,}\b"),
]
COMPILED = [(n, s, c, re.compile(p)) for (n, s, c, p) in PATTERNS]
```

扫描输出是 JSONL：`pattern`, `severity`, `category`, `match`, `source`, `line`，并把 match 截断到 80 字符，见 [secret_scan.py](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/offensive-osint/scripts/secret_scan.py:118)。

一个重要实现差异：文档表格是 48 个，但当前 `secret_scan.py` 实际 `PATTERNS` 为 47 个。缺的是文档中的“Cloudflare API Token 上下文型 40 字符 token”规则；脚本只有 `CLOUDFLARE_API` global key 形式，见 [secret_scan.py](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/offensive-osint/scripts/secret_scan.py:89)。另外 `offensive-osint/SKILL.md` 的 §48 嵌入代码仍写“29-pattern catalog”，属于旧文档残留，见 [skills/offensive-osint/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/offensive-osint/SKILL.md:4052)。

9 个 validator 定义在 [skills/offensive-osint/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/offensive-osint/SKILL.md:2271)：

| Provider | 只读验证动作 |
|---|---|
| Postman | `/me` |
| AWS | `sts:GetCallerIdentity` |
| GitHub | `/user` |
| Slack | `auth.test` |
| Anthropic | `/v1/models` |
| OpenAI | `/v1/models` |
| npm | `/-/whoami` |
| Atlassian | `/rest/api/3/myself` |
| DataDog | `/api/v1/validate` |

validator 输出 schema 包含 `status`, `provider`, `account_id`, `scope`, `metadata`, `checked_at`, `detectability`，见 [skills/offensive-osint/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/offensive-osint/SKILL.md:2386)。硬规则是只读、不得 create/modify/delete/send，并记录 UTC `checked_at`，见 [skills/offensive-osint/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/offensive-osint/SKILL.md:2402)。

**6. 严重性评分与优先级排序**

Severity anchor 在 [skills/osint-methodology/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/osint-methodology/SKILL.md:277)：

| 严重性 | 规则锚点 |
|---|---|
| `CRITICAL` | pre-auth RCE、confirmed valid credentials、listable production data、fundamental trust violations |
| `HIGH` | significant exposure with clear escalation path、高价值信息泄露 |
| `MEDIUM` | info disclosure、hardening gaps、brute-force exposure |
| `LOW` | cosmetic or marginal gaps |
| `INFO` | 值得记录但无直接行动 |

升级规则包括：login/admin/SSO 缺 HSTS 从 MED → HIGH；wildcard CORS + credentials 从 MED → HIGH；endpoint interest score ≥70 至少 HIGH；domain breach ≥10 employees 为 CRITICAL；vendor product version 命中 CISA KEV 为 CRITICAL，见 [skills/osint-methodology/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/osint-methodology/SKILL.md:289)。

Endpoint Interest Score 是 0–100 打分：unauth write +40、open GraphQL introspection +35、verb tampering +30、reflected CORS + creds +25、sensitive keyword +20、schema leak +20 等，阈值为 ≥90 CRITICAL、70–89 HIGH、50–69 MEDIUM，见 [skills/offensive-osint/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/offensive-osint/SKILL.md:1924)。

优先级排序还结合资产层 triage：WebApp 按 auth/login/sso → admin → dev/staging → API → portal/app → marketing；Email 按 exec → IT/security → dev/DBA → sales/HR/finance → role accounts；Repo 按最近 push、target name、prod/internal/secret 关键词排序，见 [skills/osint-methodology/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/osint-methodology/SKILL.md:267)。

**7. 攻击路径模板**

§39 声称用于 HIGH/CRITICAL finding 的 `attack_path_hint`，见 [skills/offensive-osint/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/offensive-osint/SKILL.md:3318)。README/frontmatter 说 27 个模板，但当前 §39 实际列出 32 个 trigger，这是另一个版本漂移。

当前模板覆盖这些触发项：unauth write、GraphQL introspection、reflected CORS + creds、wildcard CORS、verb tampering、API key in URL、schema leak、sensitive keyword、open Firebase RTDB、listable bucket、`.git` exposed、`.env` exposed、Spring actuator env/heapdump、Elasticsearch、Redis、MongoDB、subdomain takeover、kubelet、etcd、K8s anonymous API、Citrix、F5、vCenter、unauth cloud function、npm typosquat、DMARC permissive、live AI API key、public Slack invite、open Docker registry、Telegram bot token、sourcemap with `sourcesContent[]`，见 [skills/offensive-osint/SKILL.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/skills/offensive-osint/SKILL.md:3322)。

设计上它不是独立漏洞库，而是评分系统的后处理：当 finding 达到 HIGH/CRITICAL，给 operator 一个下一步验证方向，并写入 evidence 的 `attack_path_hint`。

**8. 从 Skill 内化为可编程系统能力**

要把这些方法论从 Skill 变成系统能力，建议按下面拆分：

1. **Schema 层**：把 `Asset`, `Source`, `Edge`, `Finding`, `Evidence`, `ValidationResult` 定义成 Pydantic/JSON Schema。`asset.key` 必须是 typed dedup key，例如 `sub:api.example.com`。
2. **Confidence Engine**：把 §2.1 升级表做成 per-asset-type transition rules。输入 evidence，输出新 confidence，并保留升级原因。
3. **Asset Graph Store**：用 Neo4j、Kuzu、SQLite edge table 都可以。核心是不允许裸字符串发现，所有模块输出先 upsert asset，再 attach finding。
4. **Pipeline Orchestrator**：把五阶段做成 DAG。Stage 顺序固定，stage 内模块并发；每个模块声明 input asset types、output asset types、detectability、rate limit、scope requirements。
5. **Pattern Registry**：把 48 个 secret regex 从 markdown 提取为机器可读 YAML/JSON；`secret_scan.py` 现在已经是雏形，但要修复 48 vs 47 漂移。
6. **Validator Service**：每个 provider validator 必须实现同一接口：`validate(secret) -> ValidationResult`。强制 policy gate：只读 endpoint、记录 `checked_at`、detectability、禁止写操作。
7. **Scoring Engine**：合并 severity anchors、escalation rules、endpoint interest score、EPSS/KEV enrichment、asset priority，输出排序队列。
8. **Attack Hint Renderer**：把 §39 模板变成 rule table，只有 severity ≥ HIGH 或 endpoint score ≥70 时渲染。
9. **Reporting Generator**：严格按 Finding schema 输出 JSON/YAML，再生成 client report、bug bounty report、reproduction package。
10. **Safety/RoE Gate**：把 SECURITY.md 的授权范围、只读验证、停止条件做成运行时 policy，而不是提示词约束，见 [SECURITY.md](/home/suuuu/develop/intelligence-system/archive/Claude-OSINT/SECURITY.md:14)。

最小核心模型可以长这样：

```python
class Confidence(str, Enum):
    tentative = "tentative"
    firm = "firm"
    confirmed = "confirmed"

class Asset(BaseModel):
    type: str
    key: str
    value: str
    sources: list[str]
    confidence: Confidence
    first_seen: datetime
    last_seen: datetime
    attrs: dict[str, Any] = {}

class Finding(BaseModel):
    id: str
    module: str
    asset_key: str
    category: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    confidence: Confidence
    evidence: dict[str, Any]
    remediation: str
```

我的结论：Claude-OSINT 的强项是方法论已经高度结构化，尤其是 confidence、asset graph、finding schema、severity anchors、secret catalog、validator discipline。弱点是这些结构还主要停留在 Markdown，存在几处版本漂移：asset edge schema 没有完整展开、attack-path 数量文档与实际表不一致、secret catalog 文档 48 与脚本 47 不一致。下一步要产品化，重点不是再加更多技巧，而是把这些表格转成可测试、可版本化、可执行的规则注册表。