# Design

## Architecture Notes

Initial shape:

- API/service layer: Go or Python, to be selected after reference review.
- Storage:
  - MySQL on `114` for structured entities and job state.
  - OSS-compatible object storage for static files and generated artifacts.
- Model providers:
  - NVIDIA direct API for `kimi-k2.6` and `deepseek-v4-pro`.
  - DeepSeek `deepseek-v4-pro` through Sub2API.
  - Sub2API for additional proxied models and Qiniu-backed routes.
- Documentation memory:
  - Evaluate CodeGraph for durable project documentation and code/document relationships.

## Candidate Domains

- Source ingestion
- Deduplication and normalization
- Entity extraction
- Retrieval/indexing
- Analysis workflows
- Report generation
- Audit trail

## Non-Goals For Scaffold

- No application framework selected yet.
- No database schema committed yet.
- No provider SDK committed yet.

