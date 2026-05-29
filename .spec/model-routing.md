# Model Routing SPEC

> Status: **Partially verified** — model IDs available on NVIDIA, rate limits and JSON reliability pending
> Updated: 2026-05-26

## 1. Core Principle

Do not assume any provider is unlimited or permanently free. Even on NVIDIA free tier, define timeout, retry, concurrency, and fallback.

## 2. Provider

| Provider | Role | Status |
|---|---|---|
| NVIDIA NIM | Primary | API key working, model IDs listed; rate limits pending |
| Sub2API | Fallback | Available but not yet tested for these models |

Base URL: `https://integrate.api.nvidia.com/v1` (OpenAI-compatible).

## 3. Models

| Task | Model ID | Provider | Availability |
|---|---|---|---|
| Stage 1 | `deepseek-ai/deepseek-v4-flash` | NVIDIA | Listed/available |
| Stage 2 | `deepseek-ai/deepseek-v4-pro` | NVIDIA | Listed/available |
| Digest overview | `deepseek-ai/deepseek-v4-flash` | NVIDIA | Listed/available |

## 4. Request Policy

| Setting | Stage 1 | Stage 2 | Digest |
|---|---:|---:|---:|
| Timeout | 120s | 300s | 300s |
| Concurrency | 3 | 1 | 1 |
| Retries | 2 | 2 | 2 |
| Retry backoff | exponential (2s, 4s) | exponential (5s, 10s) | exponential |
| Temperature | 0.1 | 0.2 | 0.3 |

### Output token policy

Do not set an arbitrarily small `max_tokens` that truncates quality. But do set a provider-compatible cap to prevent runaway responses:

- Stage 1: `max_tokens=2048` (structured JSON, should be ~200-500 tokens)
- Stage 2: `max_tokens=4096` (longer analysis is OK)
- Digest: `max_tokens=1024` (overview only, item summaries come from Stage 1)

If provider rejects `max_tokens`, try `max_completion_tokens`. If neither works, omit and log warning.

### Input size policy

- Prefer complete content for items under 4000 chars.
- For longer content: title + first 3000 chars + last 500 chars. Record `content_truncated=true` in metadata_json.

## 5. Output Contract

All model calls must return JSON matching expected schema.

On invalid response:
1. One retry with repair prompt ("respond with valid JSON only").
2. Still invalid → mark `stage1_error` or `stage2_error` as `model_parse_error`.
3. Do not store free-form text as valid analysis.

## 6. Fallback Policy

```text
NVIDIA deepseek-v4-flash/pro
  -> retry transient errors (timeout, 429, 500) up to 2 times
  -> Sub2API same model (if configured)
  -> mark stage-specific error = 'model_provider_error'
```

Record actual provider and model in the item's stage-specific provider/model fields.

## 7. Remaining Verification

- [x] NVIDIA API key works
- [x] deepseek-v4-flash available
- [x] deepseek-v4-pro available
- [ ] Confirm rate limit behavior (429 response shape)
- [ ] Confirm max concurrent requests allowed
- [ ] Test JSON output reliability on 5 sample items
- [ ] Test Sub2API fallback

## 8. Open Questions

| ID | Question | Default |
|---|---|---|
| M1 | What is NVIDIA's actual rate limit for free tier? | Test empirically, start conservative (3 concurrent) |
