from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import oss2

from src.pipeline.digest import DigestArtifact


class OutputError(RuntimeError):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class OSSConfig:
    endpoint: str
    bucket: str
    access_key_id: str
    access_key_secret: str
    prefix: str = "intelligence/digests"


def oss_config_from_settings() -> OSSConfig:
    from src.config import settings

    return OSSConfig(
        endpoint=settings.oss_endpoint,
        bucket=settings.oss_bucket,
        access_key_id=settings.oss_access_key_id,
        access_key_secret=settings.oss_access_key_secret,
        prefix=settings.oss_prefix,
    )


def write_hexo_post(artifact: DigestArtifact, posts_dir: str | Path) -> Path:
    target_dir = Path(posts_dir)
    if not target_dir.exists() or not target_dir.is_dir():
        raise OutputError("hexo_write_error", f"Hexo posts directory does not exist: {target_dir}")
    target_path = target_dir / artifact.hexo_path
    try:
        target_path.write_text(artifact.content_markdown, encoding="utf-8")
    except OSError as exc:
        raise OutputError("hexo_write_error", str(exc)) from exc
    return target_path


def digest_oss_key(artifact: DigestArtifact, prefix: str = "intelligence/digests") -> str:
    clean_prefix = prefix.strip("/")
    return f"{clean_prefix}/{artifact.date.isoformat()}/{artifact.domain}.md"


def upload_digest_backup(artifact: DigestArtifact, config: OSSConfig, bucket_factory=None) -> str:
    key = digest_oss_key(artifact, config.prefix)
    try:
        bucket = bucket_factory(config) if bucket_factory else _create_bucket(config)
        bucket.put_object(key, artifact.content_markdown.encode("utf-8"))
    except Exception as exc:
        raise OutputError("oss_upload_error", str(exc)) from exc

    endpoint = config.endpoint.rstrip("/")
    return f"https://{config.bucket}.{endpoint.removeprefix('https://').removeprefix('http://')}/{key}"


def _create_bucket(config: OSSConfig):
    auth = oss2.Auth(config.access_key_id, config.access_key_secret)
    return oss2.Bucket(auth, config.endpoint, config.bucket)
