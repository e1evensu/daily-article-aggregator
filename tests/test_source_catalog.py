import json

import pytest

from src.collector.catalog import as_source_model, catalog_by_id, load_source_catalog, seed_candidate_sources


def test_source_catalog_is_external_import_file_not_runtime_source_of_truth(tmp_path):
    missing = tmp_path / "missing.json"

    assert load_source_catalog(missing) == ()
    assert catalog_by_id(missing) == {}


def test_load_source_catalog_parses_external_seed_file(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "security_nvd_cve",
                    "name": "NVD CVE Feed",
                    "domain": "security",
                    "type": "api",
                    "url": "https://services.nvd.nist.gov/rest/json/cves/2.0",
                    "authority": "official",
                    "fetch_strategy": "l1_api",
                    "config_json": {"collector": "nvd"},
                }
            ]
        ),
        encoding="utf-8",
    )

    entries = load_source_catalog(path)

    assert len(entries) == 1
    assert entries[0].id == "security_nvd_cve"
    assert entries[0].status == "candidate"
    assert entries[0].config_json == {"collector": "nvd"}


def test_catalog_entries_convert_to_source_models(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "ai_hackernews",
                    "name": "Hacker News Top",
                    "domain": "ai",
                    "type": "api",
                    "url": "https://hacker-news.firebaseio.com/v0/topstories.json",
                    "authority": "authoritative",
                    "fetch_strategy": "l1_api",
                    "status": "trial",
                    "config_json": {"collector": "hackernews"},
                }
            ]
        ),
        encoding="utf-8",
    )

    model = as_source_model(catalog_by_id(path)["ai_hackernews"])

    assert model.id == "ai_hackernews"
    assert model.domain == "ai"
    assert model.type == "api"
    assert model.fetch_strategy == "l1_api"
    assert model.status == "trial"
    assert model.health == "good"
    assert model.config_json == {"collector": "hackernews"}


@pytest.mark.asyncio
async def test_seed_candidate_sources_merges_external_entries(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "security_portswigger",
                    "name": "PortSwigger Research",
                    "domain": "security",
                    "type": "rss",
                    "url": "https://portswigger.net/research/rss",
                    "authority": "authoritative",
                    "fetch_strategy": "l1_rss",
                }
            ]
        ),
        encoding="utf-8",
    )

    class FakeSession:
        def __init__(self):
            self.merged = []

        async def merge(self, source):
            self.merged.append(source)

    session = FakeSession()

    count = await seed_candidate_sources(session, path)

    assert count == 1
    assert [source.id for source in session.merged] == ["security_portswigger"]
