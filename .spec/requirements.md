# Requirements

## Product

Build a spec-driven 情报系统 for ingestion, indexing, analysis, retrieval, and report generation.

## Initial Requirements

- Support adding reference projects and reference documents before implementation.
- Keep structured metadata in MySQL on the `114` system initially.
- Store source files, generated reports, and other static artifacts in OSS-compatible storage.
- Support model calls through:
  - NVIDIA: `kimi-k2.6`, `deepseek-v4-pro`
  - DeepSeek via Sub2API reverse proxy: `deepseek-v4-pro`
  - Other Sub2API models where appropriate
- Leave room for Qiniu-backed reverse proxy paths already available through Sub2API.
- Keep project documentation persistent and queryable; evaluate `https://github.com/colbymchenry/codegraph`.

## Open Questions

- Source types: web pages, PDFs, chat logs, code repositories, databases, or manual notes?
- Required access control model?
- Expected search mode: keyword, vector, graph, or hybrid?
- Required deployment target and network boundary?

## Acceptance Criteria

- References can be dropped into `docs/references/`.
- Architecture decisions are tracked under `docs/decisions/`.
- Implementation tasks are derived from this spec before coding starts.

