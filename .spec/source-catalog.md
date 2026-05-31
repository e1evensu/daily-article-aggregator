# Source Catalog SPEC

> Status: **Partially approved** — 7 public sources approved after feed gate; internal sources and arXiv remain candidate
> Updated: 2026-05-31

## 1. Principle

Phase 1: small set of reliable L1 sources. Quality over quantity.

Approval = feed URL exists + can fetch + content is useful. Don't wait for perfect documentation.

Source IDs in this catalog are canonical API/database IDs. Use the long form exactly as listed (`security_nvd_cve`, `security_github_advisories`, `ai_hackernews`, etc.). Do not create short aliases such as `sec_nvd`, `sec_ghsa`, or `ai_hn`.

## 2. Source Status

| Status | Meaning |
|---|---|
| `candidate` | Mentioned, not tested |
| `trial` | URL known, testing |
| `approved` | Tested, content useful, parser works |
| `rejected` | Too noisy, unavailable, or out of scope |
| `deferred` | Valuable but not Phase 1 |

## 3. Source Types (Phase 1)

| Type | Phase 1 | Notes |
|---|---:|---|
| `rss` | Yes | RSS/Atom with stable URLs |
| `api` | Yes | Stable JSON API |
| `github_api` | Yes | GitHub REST/GraphQL |
| `internal_api` | Yes | SecHub/aihot after basic test |
| `http_page` | No | Phase 2 |
| `twitter_x` | No | Deferred, anti-ban review needed |
| `wechat` | No | Rejected |

## 4. Phase 1 Sources

### Security

| Source ID | Name | Type | Authority | Status |
|---|---|---|---|---|
| `security_nvd_cve` | NVD CVE Feed | api | official | approved |
| `security_github_advisories` | GitHub Security Advisories | github_api | official | approved |
| `security_portswigger` | PortSwigger Research | rss | authoritative | approved |
| `security_project_zero` | Project Zero Blog | rss | authoritative | approved |
| `security_exploitdb` | Exploit-DB | rss | authoritative | approved |
| `security_sechub` | SecHub API | internal_api | authoritative | candidate |

### AI / Tech

| Source ID | Name | Type | Authority | Status |
|---|---|---|---|---|
| `ai_aihot` | aihot API | internal_api | authoritative | candidate |
| `ai_hackernews` | Hacker News Top | api | authoritative | approved |
| `ai_arxiv` | arXiv cs.AI + cs.CR | rss | official | candidate |
| `ai_openai_blog` | OpenAI Blog | rss | official | approved |

### Deferred

| Source | Reason |
|---|---|
| X/Twitter KOL | Anti-ban review, Phase 2 |
| WeChat | Rejected, bridge fragility |
| Reddit r/netsec, r/LocalLLaMA | API noise, Phase 2 |
| Finance sources | Phase 3 |
| ProductHunt | Not core |

## 4.1 Internal API Sources Network

`security_sechub` 和 `ai_aihot` 运行在 114 上。38 通过 SSH 隧道访问，需要在 `intelligence-tunnel.service` 中增加端口转发：

\`\`\`text
-L 18210:127.0.0.1:8210    # sechub → localhost:18210
-L 18220:127.0.0.1:8220    # aihot  → localhost:18220
\`\`\`

Source URL 在 38 上应配置为 `http://127.0.0.1:18210/api/feed` 和 `http://127.0.0.1:18220/api/feed`，而非 `10.0.0.114:*`（内网 IP 从 38 不可达）。

这两个服务本身尚未部署。部署后再将 tunnel 和 source URL 加入配置。Source status 保持 `candidate` 直到服务可用。

## 5. Approval Checklist (Simplified)

A source becomes `approved` when:

- [ ] Feed/API URL is known and reachable
- [ ] Can fetch at least one real entry
- [ ] Content has signal (not pure spam/ads)
- [ ] Dedup key identified (native ID or URL)

Parser details, sample payloads, and health check rules can be refined during implementation, but `approved` status requires the checklist above to pass first.

## 6. Closed Questions

| ID | Question | Resolution |
|---|---|---|
| ~~S1~~ | Should HN be keyword-filtered before AI? | **Yes.** Filter by security/AI keywords before AI to reduce noise |
| ~~S2~~ | Should arXiv be one source or split cs.AI vs cs.CR? | **One source.** Use one `ai_arxiv` source and tag by arXiv category |
