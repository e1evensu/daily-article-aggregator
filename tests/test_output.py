from datetime import date, datetime, timezone

import pytest

from src.pipeline.digest import DigestArtifact
from src.config import settings
from src.pipeline.output import (
    OSSConfig,
    OutputError,
    digest_oss_key,
    oss_config_from_settings,
    upload_digest_backup,
    write_hexo_post,
)


def _artifact() -> DigestArtifact:
    """Build a minimal digest artifact for output-layer tests."""
    return DigestArtifact(
        id="2026-05-26:security",
        date=date(2026, 5, 26),
        domain="security",
        title="安全情报日报 · 2026-05-26",
        summary="overview",
        stats_json={},
        highlights_json=[],
        content_markdown="---\ntitle: test\n---\n\nbody\n",
        generated_at=datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc),
    )


def test_write_hexo_post_writes_fixed_filename(tmp_path):
    artifact = _artifact()

    path = write_hexo_post(artifact, tmp_path)

    assert path == tmp_path / "intelligence-security-2026-05-26.md"
    assert path.read_text(encoding="utf-8") == artifact.content_markdown


def test_write_hexo_post_raises_stable_error_when_dir_missing(tmp_path):
    with pytest.raises(OutputError) as exc:
        write_hexo_post(_artifact(), tmp_path / "missing")

    assert exc.value.category == "hexo_write_error"


def test_digest_oss_key_matches_spec_prefix():
    assert digest_oss_key(_artifact()) == "intelligence/digests/2026-05-26/security.md"


def test_upload_digest_backup_uses_bucket_and_returns_public_url():
    calls = []

    class FakeBucket:
        def put_object(self, key, content):
            calls.append((key, content))

    config = OSSConfig(
        endpoint="https://oss-cn-guangzhou.aliyuncs.com",
        bucket="suuuuzsk",
        access_key_id="id",
        access_key_secret="secret",
    )

    url = upload_digest_backup(_artifact(), config, bucket_factory=lambda config: FakeBucket())

    assert calls == [("intelligence/digests/2026-05-26/security.md", b"---\ntitle: test\n---\n\nbody\n")]
    assert url == "https://suuuuzsk.oss-cn-guangzhou.aliyuncs.com/intelligence/digests/2026-05-26/security.md"


def test_upload_digest_backup_wraps_upload_errors():
    class FailingBucket:
        def put_object(self, key, content):
            raise RuntimeError("boom")

    config = OSSConfig(
        endpoint="https://oss-cn-guangzhou.aliyuncs.com",
        bucket="suuuuzsk",
        access_key_id="id",
        access_key_secret="secret",
    )

    with pytest.raises(OutputError) as exc:
        upload_digest_backup(_artifact(), config, bucket_factory=lambda config: FailingBucket())

    assert exc.value.category == "oss_upload_error"


def test_oss_config_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "oss_endpoint", "https://oss.example.com")
    monkeypatch.setattr(settings, "oss_bucket", "bucket")
    monkeypatch.setattr(settings, "oss_access_key_id", "id")
    monkeypatch.setattr(settings, "oss_access_key_secret", "secret")
    monkeypatch.setattr(settings, "oss_prefix", "intelligence/custom")

    config = oss_config_from_settings()

    assert config == OSSConfig(
        endpoint="https://oss.example.com",
        bucket="bucket",
        access_key_id="id",
        access_key_secret="secret",
        prefix="intelligence/custom",
    )
