import argparse
import json
import subprocess
import time
import urllib.request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Docker compose release image and temporary API runtime")
    parser.add_argument("--port", type=int, default=18100, help="temporary localhost port for API smoke")
    parser.add_argument("--name", default="intel-release-smoke", help="temporary container name")
    parser.add_argument("--image", default="intelligence-system-api", help="API image name built by docker-compose")
    parser.add_argument("--timeout-s", type=float, default=60.0, help="seconds to wait for the temporary API")
    parser.add_argument("--skip-build", action="store_true", help="skip docker-compose config/build checks")
    return parser.parse_args()


def main() -> int:
    """Build or reuse the release image, boot a temp API, and smoke-test key endpoints."""
    args = parse_args()
    if not args.skip_build:
        _run(["docker-compose", "config", "--quiet"])
        _run(["docker-compose", "build"])
        _run(["docker", "run", "--rm", args.image, "python", "run_pipeline.py", "--help"], capture=True)
        _run(
            [
                "docker",
                "run",
                "--rm",
                "--env-file",
                ".env",
                args.image,
                "python",
                "-c",
                "import src.main, src.scheduler.jobs; print('ok')",
            ],
            capture=True,
        )

    container_started = False
    try:
        _run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                args.name,
                "--rm",
                "--network",
                "host",
                "--env-file",
                ".env",
                "-e",
                f"API_PORT={args.port}",
                args.image,
                "sh",
                "-c",
                f"uvicorn src.main:app --host 127.0.0.1 --port {args.port} --loop asyncio",
            ],
            capture=True,
        )
        container_started = True
        base_url = f"http://127.0.0.1:{args.port}"
        health = _wait_json(f"{base_url}/health", args.timeout_s)
        source = _wait_json(f"{base_url}/api/v1/sources/security_nvd_cve", args.timeout_s)
        if health != {"status": "ok"}:
            raise RuntimeError(f"unexpected health response: {health}")
        if source.get("data", {}).get("id") != "security_nvd_cve":
            raise RuntimeError(f"unexpected source response: {source}")
        print(json.dumps({"status": "ok", "port": args.port, "source": "security_nvd_cve"}, sort_keys=True))
        return 0
    finally:
        if container_started:
            _stop_container(args.name)


def _run(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    """Run one subprocess command, optionally capturing combined stdout/stderr."""
    return subprocess.run(
        args,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def _stop_container(name: str) -> None:
    """Best-effort stop of the temporary smoke-test container."""
    subprocess.run(["docker", "stop", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _wait_json(url: str, timeout_s: float) -> dict:
    """Poll one HTTP endpoint until it returns JSON or the timeout elapses."""
    deadline = time.monotonic() + timeout_s
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise TimeoutError(f"{url} did not return JSON within {timeout_s:.1f}s: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())
