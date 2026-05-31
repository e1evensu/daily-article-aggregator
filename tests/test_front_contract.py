import json
import subprocess
from pathlib import Path


FRONT = Path("src/front")


def _fixtures():
    """Load the front-end fixture bundle in Node and return a compact JSON summary."""
    script = """
import { FIXTURES } from './src/front/data.js';
const out = FIXTURES;
console.log(JSON.stringify({
  sourceIds: out.sources.map(s => s.id),
  sourceStatuses: out.sources.map(s => s.status),
  itemIds: out.items.map(i => i.id),
  sourceRefs: out.items.map(i => i.source_id),
  itemKeys: out.items.map(i => Object.keys(i)),
  alsoSeen: out.items.flatMap(i => i.also_seen_in || []),
  digest: out.digest
}));
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def _selector_summary():
    script = """
import {
  getActiveRun,
  modelUsage,
  retentionBuckets,
  safeRatio,
  summarizeItems,
  summarizeSources,
} from './src/front/selectors.js';
const empty = {
  activeRun: getActiveRun([]),
  sourceSummary: summarizeSources([]),
  itemSummary: summarizeItems([]),
  retention: retentionBuckets([]),
  usage: modelUsage([]),
  ratio: safeRatio(3, 0)
};
console.log(JSON.stringify(empty));
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_front_stylesheet_exists_for_index_entrypoint():
    assert (FRONT / "index.html").read_text(encoding="utf-8").count('href="styles.css"') == 1
    assert (FRONT / "styles.css").exists()


def test_front_fixture_uses_phase1_api_contract_shape():
    data = _fixtures()
    source_ids = data["sourceIds"]
    item_ids = data["itemIds"]
    source_refs = data["sourceRefs"]

    assert source_ids == [
        "security_nvd_cve",
        "security_github_advisories",
        "security_portswigger",
        "security_project_zero",
        "security_exploitdb",
        "security_sechub",
        "ai_aihot",
        "ai_hackernews",
        "ai_arxiv",
        "ai_openai_blog",
    ]
    assert set(data["sourceStatuses"]) >= {"approved", "candidate", "trial"}
    assert all(not value.startswith(("sec_", "ai_hn")) for value in source_ids + item_ids + source_refs)
    assert all(ref in source_ids for ref in source_refs)

    for keys in data["itemKeys"]:
        assert "analysis_model" not in keys
        assert "analysis_provider" not in keys
        assert "prompt_version" not in keys
        assert "analyzed_at" not in keys
        assert "stage1_model" in keys
        assert "stage1_provider" in keys
        assert "stage1_prompt_version" in keys
        assert "stage1_analyzed_at" in keys

    assert data["alsoSeen"]
    assert all(set(entry) == {"source_id", "url", "seen_at"} for entry in data["alsoSeen"])
    assert all(entry["source_id"] in source_ids for entry in data["alsoSeen"])
    assert data["digest"]["hexo_path"] == "intelligence-security-2026-05-26.md"
    assert data["digest"]["oss_url"].endswith("/intelligence/digests/2026-05-26/security.md")


def test_front_selectors_handle_empty_data():
    summary = _selector_summary()

    assert summary["activeRun"] is None
    assert summary["sourceSummary"] == {
        "approved": 0,
        "candidate": 0,
        "good": 0,
        "degraded": 0,
        "disabled": 0,
        "maxSpark": 1,
    }
    assert summary["itemSummary"] == {
        "all": 0,
        "security": 0,
        "ai": 0,
        "highValue": 0,
        "confidence": {"tentative": 0, "firm": 0, "confirmed": 0},
    }
    assert summary["retention"][0]["count"] == 0
    assert summary["usage"] == {"labels": [], "stage1": [], "stage2": []}
    assert summary["ratio"] == 0
