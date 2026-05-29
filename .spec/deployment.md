# Deployment SPEC

> Status: **Confirmed** — 关闭所有 open questions；补充 Hexo frontmatter 格式和权限要求
> Updated: 2026-05-26

## 1. Topology (Confirmed)

```text
38.38.250.196 (采集/计算, EU, 4C8G)
  Services:
    - intelligence-api      (FastAPI, port 8100, localhost only)
    - intelligence-worker   (APScheduler + pipeline)
  Network:
    - autossh tunnel → 114:3306 on localhost:13306 (MySQL)
    - autossh tunnel → 114:6379 on localhost:16379 (Redis)
    - optional autossh tunnel → 114:8210 on localhost:18210 (SecHub, only if source enabled)
    - optional autossh tunnel → 114:8220 on localhost:18220 (aihot, only if source enabled)
    - systemd: intelligence-tunnel.service (auto-start)
  Output:
    - Hexo posts → /opt/blog/source/_posts/ (digest 直接写入)

114.132.199.77 (服务机, CN, 4C4G)
  Services:
    - intelligence-mysql    (Docker, 127.0.0.1:3306)
    - intelligence-redis    (Docker, 127.0.0.1:6379)
  Storage:
    - oss2 SDK → Aliyun OSS (digest 备份，Python worker 直接上传)
  Managed by:
    - /opt/intelligence-infra/docker-compose.yml
```

## 2. Network (Confirmed)

- API binds to `127.0.0.1:8100`, not public.
- MySQL not publicly exposed (Docker binds 127.0.0.1).
- Redis not publicly exposed (Docker binds 127.0.0.1).
- 38 accesses MySQL/Redis via SSH tunnel (autossh systemd service).
- 38 accesses SecHub/aihot via SSH tunnel only after those services are deployed and the sources are promoted from `candidate`.
- 38 accesses NVIDIA and external sources over outbound HTTPS.

## 3. Docker Strategy

API and worker run in Docker on 38 with **`network_mode: host`**.

Reason: SSH tunnels bind to host's `127.0.0.1:13306` and `127.0.0.1:16379`. Containers need host network to reach these ports. Bridge mode would require tunnel rebinding or extra config.

```yaml
# docker-compose.yml on 38
services:
  api:
    build: .
    network_mode: host
    env_file: .env
    command: uvicorn src.main:app --host 127.0.0.1 --port 8100
    volumes:
      - /opt/blog/source/_posts:/opt/blog/source/_posts

  worker:
    build: .
    network_mode: host
    env_file: .env
    command: python -m src.scheduler.jobs
    volumes:
      - /opt/blog/source/_posts:/opt/blog/source/_posts
```

注意：`network_mode: host` 下 volumes 仍然需要显式挂载，因为容器文件系统是隔离的。API 和 worker 都需要访问 Hexo 目录（worker 写入，API 可选读取验证）。

## 4. Credentials (Confirmed)

| Variable | Source | Status |
|---|---|---|
| DATABASE_URL | .env | Written, tested |
| REDIS_URL | .env | Written, tested |
| NVIDIA_API_KEY | .env (from master.env) | Verified, models confirmed |
| NVIDIA_BASE_URL | .env | `https://integrate.api.nvidia.com/v1` |
| OSS_* | .env (from master.env) | Written |
| GITHUB_TOKEN | .env (from master.env) | Written |
| FEISHU_APP_* | .env (from master.env) | Written, webhook URL pending |

All credentials in `.env` (chmod 600), not in git.

## 5. Digest Publication

### 5.1 Hexo Post（主路径）

```text
/opt/blog/source/_posts/
  intelligence-security-YYYY-MM-DD.md
  intelligence-ai-YYYY-MM-DD.md
```

文件名格式固定，Hexo 按 frontmatter 中的 date 排序。

Frontmatter:

```yaml
---
title: 安全情报日报 · 2026-05-26
date: 2026-05-26 08:06:00
tags:
  - intelligence
  - security
categories:
  - 情报日报
---
```

权限要求：
- Worker 进程（或容器用户）需要对 `/opt/blog/source/_posts/` 有写权限
- 建议 chown 给 intelligence 用户，或确保 Docker 容器以有权限的 uid 运行
- 写入前检查目录存在，不存在则 `hexo_write_error`

### 5.2 OSS 备份

Bucket: `suuuuzsk`
Prefix: `intelligence/`

```text
intelligence/
  digests/
    YYYY-MM-DD/
      security.md
      ai.md
```

OSS 上传失败仅 log warning，不影响 run status。

## 6. Logging

- Structured JSON logs via Python logging.
- One run summary per run (logged + stored in runs table).
- No prompt content in normal logs.
- Debug mode via LOG_LEVEL=debug.

## 7. Backup

- MySQL: Docker volume on 114, manual mysqldump or existing backup policy.
- OSS digests: durable by design.
- Logs: rotated locally.

## 8. Open Questions

_None — all resolved._

| ID | Question | Resolution |
|---|---|---|
| ~~DEP1~~ | Hexo post write path and permissions | 路径确认为 `/opt/blog/source/_posts/`，Docker volume 挂载解决权限，部署前需 smoke test 写入 |
