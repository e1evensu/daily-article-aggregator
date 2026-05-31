import asyncio
import argparse
import json
import sys
import time
from pathlib import Path

from src.ai.analyzer import Analyzer
from src.config import settings

SOURCE = {"name": "Test Security Feed", "authority": "authoritative"}
SAMPLE_PROCESS_GRACE_S = 30.0
SAMPLES = [
    {
        "title": "CVE-2025-1234: Unauthenticated RCE in Apache Struts 2 via OGNL",
        "canonical_url": "https://example.test/cve-2025-1234",
        "published_at": None,
        "content_text": (
            "A critical remote code execution vulnerability (CVSS 9.8) affects Apache Struts 2 "
            "versions 2.5.0-2.5.32. Unauthenticated attackers can execute arbitrary code by sending "
            "crafted OGNL expressions in multipart form fields. A public proof-of-concept exploit is "
            "already circulating and active exploitation has been observed in the wild. Patch to 6.4.0."
        ),
    },
    {
        "title": "Prompt injection via zero-width unicode bypasses LLM content filters",
        "canonical_url": "https://example.test/llm-injection",
        "published_at": None,
        "content_text": (
            "Researchers demonstrate a prompt-injection technique that smuggles hidden instructions "
            "into LLM applications using zero-width unicode characters, evading naive content filters. "
            "The paper includes mitigations: unicode normalization and instruction-data separation."
        ),
    },
    {
        "title": "Weekly roundup: misc security news and conference dates",
        "canonical_url": "https://example.test/roundup",
        "published_at": None,
        "content_text": (
            "A grab-bag of links this week: a few conference CFP deadlines, a vendor blog about their "
            "new dashboard UI, and a reminder to update your password manager. Nothing critical."
        ),
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Stage-1 JSON and NVIDIA concurrency behavior")
    parser.add_argument(
        "--sample-timeout-s",
        type=float,
        default=settings.stage1_timeout_s + SAMPLE_PROCESS_GRACE_S,
        help=(
            "maximum seconds per sample subprocess; the model request still uses "
            "STAGE1_TIMEOUT_S, with extra process cleanup grace"
        ),
    )
    parser.add_argument("--sample-attempts", type=int, default=2, help="hard-timeout attempts per sample")
    parser.add_argument("--concurrency-timeout-s", type=float, default=180.0, help="maximum seconds for concurrent requests")
    parser.add_argument("--concurrency", type=int, default=settings.stage1_concurrency, help="concurrent Stage-1 requests to gate")
    parser.add_argument("--min-concurrent-ok", type=int, default=settings.stage1_concurrency, help="minimum successful concurrent requests")
    parser.add_argument(
        "--stress-concurrency",
        type=int,
        default=0,
        help="optional extra stress probe; failures are reported but do not fail the gate",
    )
    parser.add_argument("--check-sample", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--check-concurrency", type=int, help=argparse.SUPPRESS)
    return parser.parse_args()


async def main():
    """Run the full AI gate or one targeted subprocess probe."""
    args = parse_args()
    if not settings.nvidia_api_key:
        print("FAIL gate: NVIDIA_API_KEY is not configured", flush=True)
        return 2

    failures = 0

    if args.check_sample is not None:
        return await _check_sample(args.check_sample)
    if args.check_concurrency is not None:
        return await _check_concurrency(args.check_concurrency)

    print("=== Gate: Stage-1 JSON output on samples ===", flush=True)
    for idx, sample in enumerate(SAMPLES):
        result = await _run_sample_with_attempts(idx, attempts=args.sample_attempts, timeout_s=args.sample_timeout_s)
        if result.get("status") == "succeeded":
            print(
                f"OK {float(result['duration_s']):4.1f}s score={result['insight_score']} "
                f"cat={result['category']} cred={result['credibility']} tags={result['tags']} "
                f"model={result['model']} err=None | {sample['title'][:45]}",
                flush=True,
            )
        else:
            failures += 1
            error = result.get("error") or result.get("status") or "unknown_error"
            print(
                f"FAIL {float(result['duration_s']):4.1f}s err={error} "
                f"| {sample['title'][:45]}",
                flush=True,
            )

    ok = await _run_concurrency_probe(
        concurrency=args.concurrency,
        timeout_s=args.concurrency_timeout_s,
        min_ok=args.min_concurrent_ok,
        fail_gate=True,
    )
    if not ok:
        failures += 1

    if args.stress_concurrency:
        await _run_concurrency_probe(
            concurrency=args.stress_concurrency,
            timeout_s=args.concurrency_timeout_s,
            min_ok=args.stress_concurrency,
            fail_gate=False,
        )

    if failures:
        print(f"FAIL gate: {failures} check(s) failed", flush=True)
        return 1
    print("OK gate: Stage-1 JSON and rate-limit checks passed", flush=True)
    return 0


async def _run_concurrency_probe(
    *,
    concurrency: int,
    timeout_s: float,
    min_ok: int,
    fail_gate: bool,
) -> bool:
    """Run one subprocess concurrency probe and print a human-readable summary."""
    label = "Gate" if fail_gate else "Stress"
    print(f"=== {label}: rate limit — {concurrency} concurrent requests ===", flush=True)
    result = await _run_subprocess(["--check-concurrency", str(concurrency)], timeout_s=timeout_s)
    if result.get("status") == "gate_timeout":
        print(f"FAIL {label.lower()}: {concurrency} concurrent requests exceeded {timeout_s:.1f}s", flush=True)
        return False

    ok = int(result.get("ok") or 0)
    errs = result.get("errors") or []
    exc = result.get("exceptions") or []
    status = "OK" if ok >= min_ok else "FAIL"
    print(
        f"{status} {concurrency} concurrent in {float(result['duration_s']):.1f}s: "
        f"ok={ok}/{concurrency} errors={errs} exceptions={exc}",
        flush=True,
    )
    return ok >= min_ok


async def _run_sample_with_attempts(index: int, *, attempts: int, timeout_s: float) -> dict:
    """Retry one sample probe under a hard subprocess timeout."""
    last_result = {"status": "failed", "duration_s": 0.0, "error": "not_attempted"}
    for attempt in range(1, max(1, attempts) + 1):
        result = await _run_subprocess(["--check-sample", str(index)], timeout_s=timeout_s)
        result["attempt"] = attempt
        if result.get("status") == "succeeded":
            return result
        last_result = result
        print(
            f"WARN sample {index} attempt {attempt}/{attempts} failed: {result.get('error') or result.get('status')}",
            flush=True,
        )
    return last_result


async def _run_subprocess(args: list[str], *, timeout_s: float) -> dict:
    """Run one gate subprocess and normalize its JSON or failure output."""
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).resolve()),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"status": "gate_timeout", "duration_s": time.monotonic() - started}

    output = stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        error = stderr.decode("utf-8", errors="replace").strip() or output or "gate_subprocess_failed"
        return {"status": "failed", "duration_s": time.monotonic() - started, "error": error.splitlines()[-1][:200]}
    try:
        return json.loads(output.splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"status": "failed", "duration_s": time.monotonic() - started, "error": "gate_bad_output"}


async def _check_sample(index: int) -> int:
    """Run stage-1 analysis for one sample and print a machine-readable JSON result."""
    az = Analyzer.nvidia_from_settings()
    started = time.time()
    try:
        out = await az.analyze_stage1(SAMPLES[index], SOURCE)
        duration = time.time() - started
        if out.analysis is None:
            print(json.dumps({"status": "failed", "duration_s": duration, "error": out.error}), flush=True)
            return 0
        print(
            json.dumps(
                {
                    "status": "succeeded",
                    "duration_s": duration,
                    "insight_score": out.analysis.insight_score,
                    "category": out.analysis.category,
                    "credibility": out.analysis.credibility,
                    "tags": out.analysis.tags,
                    "model": out.model,
                }
            ),
            flush=True,
        )
        return 0
    finally:
        await az.client.aclose()


async def _check_concurrency(concurrency: int) -> int:
    """Run concurrent stage-1 analyses and print a machine-readable concurrency summary."""
    az = Analyzer.nvidia_from_settings()
    started = time.time()
    try:
        res = await asyncio.gather(
            *[az.analyze_stage1(SAMPLES[0], SOURCE) for _ in range(concurrency)],
            return_exceptions=True,
        )
        duration = time.time() - started
        print(
            json.dumps(
                {
                    "status": "completed",
                    "duration_s": duration,
                    "ok": sum(1 for r in res if not isinstance(r, Exception) and r.analysis),
                    "errors": [r.error for r in res if not isinstance(r, Exception) and not r.analysis],
                    "exceptions": [type(r).__name__ for r in res if isinstance(r, Exception)],
                }
            ),
            flush=True,
        )
        return 0
    finally:
        await az.client.aclose()


sys.exit(asyncio.run(main()))
