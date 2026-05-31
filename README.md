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
- Current technical debt review: `docs/TECH_DEBT_REVIEW.md`
- Reference drop zone: `docs/references/`

## Comment Policy

The repository keeps comment policy in `docs/ARCHITECTURE.md`.

- `make check-comments`: run the lightweight repository comment-policy check
- `make check-migrations`: verify numbered SQL migration naming and discovery
- `make check-frontend`: enforce the current front-end window-export whitelist
- `make lint`: runs Ruff plus the comment-policy check
- `make verify`: runs lint, tests, and compile checks

The policy intentionally targets active Python code and root scripts first. It
does not require every function to have a docstring, and it rejects the most
obvious mechanical `Return ...` style docstrings on non-test code.

## Runtime Notes

- `DATABASE_VERIFY_TLS=false` keeps the current cross-border deployment behavior:
  encrypt MySQL traffic but accept the service's self-signed certificate.
- Set `DATABASE_VERIFY_TLS=true` only after the runtime can present a verifiable
  certificate chain and hostname.
