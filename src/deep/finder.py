#!/usr/bin/env python3
"""Deep-analysis "Finder" stage for the intelligence system.

Turns a security advisory into a code-grounded root-cause report by running the
pi agent (via sub2api / NVIDIA, rotating across providers) against the
*vulnerable* repository checkout, NDayBench-style: qualify -> checkout the fix
commit's first parent (pre-patch) -> let pi trace source->sink with read-only
tools -> save a structured report.

Provider rotation avoids hanging on a single RPM-limited group: each analysis
tries candidates in order and falls back to the next on empty/failed output.

Standalone (stdlib only). Importable for pipeline wiring, or run as a CLI:

    python3 src/deep/finder.py ghsa GHSA-xxxx-xxxx-xxxx

Env: GITHUB_TOKEN, PI_BIN, DEEP_MODELS ("prov/model,prov/model,..."),
     DEEP_RATE_DELAY (seconds between pi attempts), DEEP_WORK_ROOT, DEEP_REPORT_DIR.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
PI_BIN = os.environ.get("PI_BIN", "/root/.hermes/node/bin/pi")
WORK_ROOT = os.environ.get("DEEP_WORK_ROOT", "/tmp/deepwork")
REPORT_DIR = os.environ.get("DEEP_REPORT_DIR", "/root/intel-deep/reports")
# Round-robin DISPATCHER: the primaries take turns being the main engine across
# analyses (analysis 1 -> primary[0], analysis 2 -> primary[1], ...), so each
# provider only sees ~half the traffic and neither hits its RPM limit. The other
# primary (and any fallbacks) act as failover within a single analysis.
DEEP_PRIMARIES = os.environ.get(
    "DEEP_PRIMARIES", "sub2api/claude-sonnet-4-6,nvidia/deepseek-ai/deepseek-v4-flash")
DEEP_FALLBACKS = os.environ.get("DEEP_FALLBACKS", "sub2api/claude-opus-4-7")
DEEP_RATE_DELAY = float(os.environ.get("DEEP_RATE_DELAY", "3"))  # gentle pacing between attempts
RR_STATE = os.environ.get("DEEP_RR_STATE", "/root/intel-deep/.rr")

COMMIT_RE = re.compile(r"github\.com/([^/\s]+/[^/\s]+)/commit/([0-9a-f]{7,40})", re.I)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True, file=sys.stderr)


def _parse_models(spec: str):
    """Parse a comma-separated provider/model spec into tuples."""
    out = []
    for tok in spec.split(","):
        tok = tok.strip()
        if tok and "/" in tok:
            provider, model = tok.split("/", 1)
            out.append((provider, model))
    return out


def _next_rr() -> int:
    """Persistent round-robin counter shared across all analyses."""
    try:
        n = int(Path(RR_STATE).read_text().strip())
    except Exception:
        n = 0
    try:
        Path(RR_STATE).parent.mkdir(parents=True, exist_ok=True)
        Path(RR_STATE).write_text(str(n + 1))
    except Exception:
        pass
    return n


def dispatch_order():
    """Round-robin the primaries (so providers alternate as main engine across
    analyses), then append fallbacks. Returns the ordered candidate list."""
    primaries = _parse_models(DEEP_PRIMARIES)
    fallbacks = _parse_models(DEEP_FALLBACKS)
    if not primaries:
        return fallbacks
    off = _next_rr() % len(primaries)
    rotated = primaries[off:] + primaries[:off]
    # de-dupe fallbacks already present as a primary
    seen = set(rotated)
    return rotated + [c for c in fallbacks if c not in seen]


def _gh_get(url: str):
    """Fetch one GitHub API JSON document using the configured token when present."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "intel-deep"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_advisory(ghsa: str) -> dict:
    """Fetch one GitHub security advisory payload by GHSA id."""
    return _gh_get(f"https://api.github.com/advisories/{ghsa}")


def qualify(adv: dict):
    """NDayBench-style filter. Return (slug, fix_sha) if deep-analyzable, else None."""
    repo = adv.get("source_code_location") or ""
    repo_slug = re.sub(r"^https?://github\.com/", "", repo).strip("/").lower() if repo else None

    commits = []
    for ref in list(adv.get("references", []) or []):
        url = ref if isinstance(ref, str) else (ref or {}).get("url", "")
        m = COMMIT_RE.search(url or "")
        if m:
            commits.append((m.group(1), m.group(2)))
    if not commits:
        return None

    chosen = None
    if repo_slug:
        for slug, sha in commits:
            if slug.lower() == repo_slug:
                chosen = (slug, sha)
                break
    return chosen or commits[0]


def prepare_repo(slug: str, sha: str):
    """Clone and check out the vulnerable state (fix commit's first parent)."""
    work = Path(WORK_ROOT) / slug.replace("/", "__")
    if work.exists():
        subprocess.run(["rm", "-rf", str(work)], check=False)
    work.parent.mkdir(parents=True, exist_ok=True)

    log(f"cloning {slug} (blob:none) ...")
    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--quiet", f"https://github.com/{slug}", str(work)],
        check=True, timeout=900,
    )

    def git(*args):
        return subprocess.run(["git", "-C", str(work), *args], capture_output=True, text=True)

    git("fetch", "--quiet", "origin", sha)
    parent = git("rev-parse", f"{sha}^1").stdout.strip()
    if not parent:
        raise RuntimeError(f"cannot resolve first parent of {sha}")
    fix_diff = git("diff", parent, sha).stdout
    r = git("checkout", "-q", parent)
    if r.returncode != 0:
        raise RuntimeError(f"checkout failed: {r.stderr}")
    log(f"checked out vulnerable state {parent[:10]}")
    return str(work), parent, fix_diff


def build_security_prompt(adv: dict, slug: str) -> str:
    """Build the read-only RCA prompt passed to pi for one advisory analysis."""
    return f"""You are a security vulnerability analyst (a "Finder"). The current working directory is a checkout of `{slug}` at a commit that still contains a KNOWN, unpatched security vulnerability:

- {adv.get('ghsa_id')} / {adv.get('cve_id')}
- Severity: {adv.get('severity')}
- Summary: {adv.get('summary')}

Use your read and bash tools to do a grounded root-cause analysis. This is READ-ONLY auditing — do NOT modify, create, or delete any files. Work like a human auditor: read the code and follow attacker-controlled data to the dangerous operation.

Produce a precise, code-grounded report with EXACTLY these sections:
1. **Sink** — the exact file, function, and line where attacker-controlled data reaches a dangerous operation. Quote the code.
2. **Source** — where attacker-controlled input enters (route/handler/parameter). Quote it.
3. **Source→Sink data flow** — every function and variable the tainted value passes through, each with a `file:line` citation. No hand-waving; if you assert a step you must have read it.
4. **Root cause** — exactly what validation/canonicalization is missing.
5. **Proof of Concept** — a concrete request/input that exploits it.
6. **Fix** — the correct fix, and how to verify it.

Cite real file:line from THIS checkout. Ground every claim in code you actually read."""


def _run_pi(workdir: str, prompt: str, provider: str, model: str, timeout: int):
    """Run one pi analysis attempt with the given provider/model pair."""
    p = subprocess.run(
        [PI_BIN, "-p", prompt, "--provider", provider, "--model", model,
         "--no-session", "--exclude-tools", "edit,write"],
        cwd=workdir, capture_output=True, text=True, timeout=timeout,
    )
    return p.stdout.strip(), p.stderr.strip()


def run_finder_rotating(workdir: str, prompt: str, timeout: int = 3300):
    """Dispatch via round-robin (providers alternate as primary across analyses),
    falling back to the next candidate on empty output. Returns
    (report, used_model, attempts)."""
    order = dispatch_order()
    log("dispatch order: " + " -> ".join(f"{p}/{m}" for p, m in order))
    attempts = []
    for provider, model in order:
        log(f"finder attempt: {provider}/{model} ...")
        try:
            out, err = _run_pi(workdir, prompt, provider, model, timeout)
        except subprocess.TimeoutExpired:
            out, err = "", "timeout"
        attempts.append({"provider": provider, "model": model, "ok": bool(out), "err": err[:200]})
        if out:
            log(f"  -> ok via {provider}/{model} ({len(out)} chars)")
            return out, f"{provider}/{model}", attempts
        log(f"  -> empty via {provider}/{model} (err: {err[:120]}); rotating")
        time.sleep(DEEP_RATE_DELAY)
    return "", "", attempts


def save_report(subject: str, report: str, meta: dict, *, sidecar: str | None = None,
                sidecar_name: str | None = None) -> str:
    """Write `{subject}.md` with a machine-readable meta header and a kind-aware
    human header. Optionally drop a sidecar file (vuln: the fix diff = answer
    key; paper: the extracted paper text)."""
    Path(REPORT_DIR).mkdir(parents=True, exist_ok=True)
    rp = Path(REPORT_DIR) / f"{subject}.md"
    kind = meta.get("kind", "vuln_rca")
    if kind == "paper_breakdown":
        title = f"# Deep Paper Breakdown — {subject}\n"
        sub = (f"> paper **{meta.get('title', '')}** · repo `{meta.get('repo') or '—'}` "
               f"· model {meta.get('model')}\n\n")
    else:
        title = f"# Deep RCA — {subject}\n"
        sub = (f"> repo `{meta.get('repo')}` @ vulnerable `{meta.get('vuln_commit', '')[:12]}` "
               f"(fix `{meta.get('fix_commit', '')[:12]}`) · model {meta.get('model')}\n\n")
    header = f"<!-- {json.dumps(meta, ensure_ascii=False)} -->\n\n{title}{sub}"
    rp.write_text(header + report, encoding="utf-8")
    if sidecar is not None and sidecar_name:
        Path(REPORT_DIR, sidecar_name).write_text(sidecar, encoding="utf-8")
    return str(rp)


def deep_analyze_advisory(ghsa: str) -> dict | None:
    """Run the full deep RCA flow for one GHSA advisory and persist its report on disk."""
    adv = fetch_advisory(ghsa)
    q = qualify(adv)
    if not q:
        log(f"{ghsa}: NOT qualified (needs explicit repo + fix commit)")
        return None
    slug, sha = q
    workdir, vuln_commit, fix_diff = prepare_repo(slug, sha)
    prompt = build_security_prompt(adv, slug)
    report, used, attempts = run_finder_rotating(workdir, prompt)
    status = "ok" if report else "empty"
    meta = {"ghsa": ghsa, "cve": adv.get("cve_id"), "repo": slug,
            "vuln_commit": vuln_commit, "fix_commit": sha, "model": used,
            "status": status, "attempts": attempts}
    report_path = save_report(
        ghsa, report or "(all providers returned empty)", meta,
        sidecar=fix_diff, sidecar_name=f"{ghsa}.fixdiff.patch",
    )
    meta["report_path"] = report_path
    meta["report_len"] = len(report)
    return meta


# ---------------------------------------------------------------------------
# AI-paper deep dive (DeepCode-inspired). Fetch the paper text + its official
# code repo, then have pi produce a method breakdown *grounded in the released
# code* — not a reproduction. Reuses the same rotating dispatcher / report sink.
# ---------------------------------------------------------------------------

ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(?:v\d+)?")
GITHUB_LINK_RE = re.compile(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", re.I)
# Non-repo paths that show up as github.com/<x>/<y> but aren't code repos.
_REPO_BLOCK_OWNERS = {"sponsors", "features", "about", "pricing", "topics", "site",
                      "readme", "marketplace", "settings", "notifications", "apps"}


class _HTMLText(HTMLParser):
    """Minimal, dependency-free HTML->text: drop script/style/nav, insert
    newlines around block elements so section structure survives."""

    _SKIP = {"script", "style", "head", "nav", "footer", "noscript"}
    _BLOCK = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5",
              "li", "tr", "br", "blockquote", "pre"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        """Track skipped regions and preserve block boundaries on opening tags."""
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        """Track skipped regions and preserve block boundaries on closing tags."""
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        """Accumulate visible text outside skipped HTML regions."""
        if self._skip == 0:
            self.parts.append(data)

    def text(self) -> str:
        """Return normalized text extracted from the HTML document."""
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in "".join(self.parts).splitlines()]
        out, blanks = [], 0
        for ln in lines:
            if ln:
                out.append(ln)
                blanks = 0
            elif blanks < 1:  # collapse runs of blank lines to one
                out.append("")
                blanks += 1
        return "\n".join(out).strip()


def _http_get(url: str, timeout: int = 40, accept: str = "*/*"):
    """Fetch one text resource over HTTP using only stdlib networking."""
    req = urllib.request.Request(url, headers={"User-Agent": "intel-deep", "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _http_get_json(url: str, timeout: int = 30):
    """Fetch one JSON resource over HTTP using only stdlib networking."""
    return json.loads(_http_get(url, timeout=timeout, accept="application/json"))


def normalize_arxiv_id(s: str) -> str:
    """Extract the canonical arXiv identifier from a URL or free-form string."""
    m = ARXIV_ID_RE.search(s or "")
    return m.group(1) if m else (s or "").strip()


def fetch_arxiv_meta(arxiv_id: str) -> dict:
    """arXiv Atom API -> title / summary / authors / categories."""
    try:
        xml = _http_get(f"https://export.arxiv.org/api/query?id_list={arxiv_id}", timeout=30)
    except Exception as e:  # noqa: BLE001
        log(f"arxiv meta fetch failed: {e}")
        return {"arxiv_id": arxiv_id}

    # Scope to the <entry> block — the feed itself has a <title> ("arXiv Query
    # ...") that would otherwise shadow the paper's real title.
    em = re.search(r"<entry>(.*?)</entry>", xml, re.S)
    entry = em.group(1) if em else xml

    def pick(tag):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", entry, re.S)
        return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    authors = [a.strip() for a in re.findall(r"<name>(.*?)</name>", entry, re.S)]
    cats = re.findall(r'<category[^>]*term="([^"]+)"', entry)
    return {"arxiv_id": arxiv_id, "title": pick("title"), "summary": pick("summary"),
            "authors": authors[:12], "categories": cats}


def fetch_paper_text(arxiv_id: str):
    """Prefer arXiv's LaTeX-rendered HTML (clean, full text); fall back to
    ar5iv. Returns (text, source_url, raw_html). raw_html is kept so repo
    discovery can mine <a href> links the stripped text would lose."""
    for url in (f"https://arxiv.org/html/{arxiv_id}", f"https://ar5iv.org/abs/{arxiv_id}"):
        try:
            raw = _http_get(url, timeout=60)
        except Exception:
            continue
        ex = _HTMLText()
        try:
            ex.feed(raw)
        except Exception:
            continue
        txt = ex.text()
        if len(txt) > 2000:
            log(f"paper text from {url} ({len(txt)} chars)")
            return txt, url, raw
    log("no HTML full text; will analyze from abstract + code only")
    return "", "", ""


def find_paper_repo(arxiv_id: str, paper_text: str, meta: dict, raw_html: str = ""):
    """Locate the paper's official code repo. Try Papers-with-Code (official
    flag / most stars) first, then GitHub links mined from the raw paper HTML
    (hrefs + visible text) and abstract."""
    # 1) Papers-with-Code
    try:
        papers = _http_get_json(
            f"https://paperswithcode.com/api/v1/papers/?arxiv_id={arxiv_id}", timeout=25)
        results = papers.get("results") or []
        if results:
            pid = results[0].get("id")
            repos = _http_get_json(
                f"https://paperswithcode.com/api/v1/papers/{pid}/repositories/", timeout=25)
            rlist = repos.get("results") or []
            rlist.sort(key=lambda r: (bool(r.get("is_official")), r.get("stars") or 0), reverse=True)
            for r in rlist:
                m = GITHUB_LINK_RE.search(r.get("url") or "")
                if m:
                    slug = m.group(1).removesuffix(".git")
                    log(f"repo via paperswithcode: {slug} (official={r.get('is_official')}, stars={r.get('stars')})")
                    return slug
    except Exception as e:  # noqa: BLE001
        log(f"paperswithcode lookup failed: {e}")

    # 2) Mine GitHub links from the raw HTML (catches <a href> repo links that
    #    don't appear in the stripped text), plus visible text + abstract.
    blob = (raw_html or "") + "\n" + (paper_text or "") + "\n" + (meta.get("summary") or "")
    counts: dict[str, int] = {}
    for m in GITHUB_LINK_RE.finditer(blob):
        slug = m.group(1).removesuffix(".git").rstrip(".,);")
        owner = slug.split("/", 1)[0].lower()
        if owner in _REPO_BLOCK_OWNERS or slug.count("/") != 1:
            continue
        counts[slug] = counts.get(slug, 0) + 1
    if counts:
        # Most-mentioned repo is almost always the paper's own; the clone step is
        # the real validator (bad slug -> clone fails -> analyze from text).
        slug = max(counts.items(), key=lambda kv: kv[1])[0]
        log(f"repo via paper links: {slug} (mentions={counts[slug]})")
        return slug
    log("no official code repo found")
    return None


def prepare_paper(arxiv_id: str, paper_text: str, slug):
    """Lay out a work dir with paper.txt and (if found) the cloned repo under
    code_base/, so pi can read both with read-only tools."""
    work = Path(WORK_ROOT) / f"arxiv__{arxiv_id}"
    if work.exists():
        subprocess.run(["rm", "-rf", str(work)], check=False)
    work.mkdir(parents=True, exist_ok=True)
    (work / "paper.txt").write_text(
        paper_text or "(full text unavailable; analyze from abstract + code)", encoding="utf-8")

    repo_dir = None
    if slug:
        dest = work / "code_base"
        log(f"cloning paper repo {slug} ...")
        try:
            subprocess.run(
                ["git", "clone", "--filter=blob:none", "--depth", "1", "--quiet",
                 f"https://github.com/{slug}", str(dest)],
                check=True, timeout=900,
            )
            repo_dir = str(dest)
        except Exception as e:  # noqa: BLE001
            log(f"repo clone failed ({slug}): {e}")
    return str(work), repo_dir


def build_paper_prompt(meta: dict, slug, has_text: bool) -> str:
    """Build the read-only paper-breakdown prompt passed to pi."""
    repo_line = (
        "The official code is cloned under `code_base/`. GROUND every "
        "implementation claim in files you actually read there (cite `file:line`)."
        if slug else
        "No official code repo was found — analyze from the paper text, and say so explicitly."
    )
    text_line = ("The full paper text is in `paper.txt`." if has_text
                 else "Full text was unavailable; the abstract is below — lean on the code.")
    return f"""You are a senior researcher writing a deep technical breakdown of an academic paper for an expert audience. This is ANALYSIS, not reproduction — do NOT write new code or modify anything (read-only).

- arXiv: {meta.get('arxiv_id')}
- Title: {meta.get('title')}
- Authors: {', '.join(meta.get('authors', [])[:8])}
- Categories: {', '.join(meta.get('categories', []))}
- Abstract: {meta.get('summary')}

{text_line} {repo_line}

Use your read and bash tools. Produce a precise breakdown with EXACTLY these sections:
1. **Problem & contribution** — the exact problem, and what is genuinely new vs prior work.
2. **Method decomposition** — the core method broken into components: architecture, key algorithms (by name), and the important formulas/objectives. Be concrete.
3. **Implementation grounding** — map each major method component to where it lives in `code_base/` (module/file/function, with `file:line`). If the code is absent or differs, say so.
4. **Paper ↔ code consistency** — does the released code actually implement the paper's claims? Note anything missing, simplified, or *extra* (undisclosed tricks, hyperparameters, engineering that matters but isn't in the paper).
5. **How to run it** — real entry points, expected data/inputs, configs, and the commands a practitioner would use (from the repo).
6. **Critical assessment** — strengths, limitations, failure modes, and what a practitioner should know before adopting it.

Ground every claim in the paper text or code you actually read. No hand-waving."""


def deep_analyze_paper(arxiv_id: str) -> dict:
    """Run the full deep paper-breakdown flow for one arXiv paper."""
    arxiv_id = normalize_arxiv_id(arxiv_id)
    meta_a = fetch_arxiv_meta(arxiv_id)
    paper_text, source, raw_html = fetch_paper_text(arxiv_id)
    slug = find_paper_repo(arxiv_id, paper_text, meta_a, raw_html)
    workdir, repo_dir = prepare_paper(arxiv_id, paper_text, slug)
    prompt = build_paper_prompt(meta_a, slug, bool(paper_text))
    report, used, attempts = run_finder_rotating(workdir, prompt)
    status = "ok" if report else "empty"
    meta = {"subject": arxiv_id, "kind": "paper_breakdown", "title": meta_a.get("title"),
            "repo": slug, "paper_source": source, "model": used,
            "status": status, "attempts": attempts}
    report_path = save_report(
        arxiv_id, report or "(all providers returned empty)", meta,
        sidecar=(paper_text or None),
        sidecar_name=(f"{arxiv_id}.paper.txt" if paper_text else None),
    )
    meta["report_path"] = report_path
    meta["report_len"] = len(report)
    return meta


def main():
    """Run the Finder CLI in GHSA or paper-analysis mode."""
    ap = argparse.ArgumentParser(description="Deep-analysis Finder")
    sub = ap.add_subparsers(dest="mode", required=True)
    g = sub.add_parser("ghsa", help="security advisory RCA")
    g.add_argument("id", help="GHSA id")
    p = sub.add_parser("paper", help="AI-paper method breakdown")
    p.add_argument("id", help="arXiv id, e.g. 2512.07921")
    a = ap.parse_args()
    r = deep_analyze_advisory(a.id) if a.mode == "ghsa" else deep_analyze_paper(a.id)
    print(json.dumps(r, ensure_ascii=False, indent=2) if r else "NOT QUALIFIED")


if __name__ == "__main__":
    main()
