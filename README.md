# Intelligence System

中文名：情报系统

Spec-first project scaffold. Put reference projects and reference documents under `docs/references/`.

## Current Scope

- Collect, organize, analyze, and retrieve intelligence material.
- Prefer Go or Python after references are reviewed.
- Persist core structured data in MySQL on the `114` system for now.
- Store static files and large artifacts in OSS-compatible storage.
- Use small-task models through NVIDIA, DeepSeek, or Sub2API-proxied providers.

## Project Docs

Current SPECs are draft review documents. They are meant for analysis before implementation.

- Requirements: `.spec/requirements.md`
- Design: `.spec/design.md`
- Tasks and review gates: `.spec/tasks.md`
- Source catalog: `.spec/source-catalog.md`
- Data model: `.spec/data-model.md`
- Pipeline: `.spec/pipeline.md`
- Model routing: `.spec/model-routing.md`
- API: `.spec/api.md`
- Deployment: `.spec/deployment.md`
- Review checklist: `.spec/review-checklist.md`
- Architecture decisions: `docs/decisions/`
- Reference drop zone: `docs/references/`
