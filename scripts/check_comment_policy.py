#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGETS = [
    ROOT / "src",
    ROOT / "add_sources.py",
    ROOT / "ai_gate_test.py",
    ROOT / "migrate.py",
    ROOT / "run_pipeline.py",
    ROOT / "seed_sources.py",
    ROOT / "verify_feeds.py",
    ROOT / "verify_production.py",
    ROOT / "verify_release.py",
]

DISCOURAGED_PREFIXES = ("Return ",)

REQUIRED_FUNC_NAMES = {
    "run_with_lifecycle",
    "run_daily_pipeline",
    "collect_sources",
    "fetch_source",
    "normalize_raw_item",
    "build_digest_artifact",
    "write_hexo_post",
    "upload_digest_backup",
}


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for target in TARGETS:
        if target.is_file():
            files.append(target)
        else:
            files.extend(sorted(target.rglob("*.py")))
    return files


def should_require_docstring(path: Path, node: ast.AST) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name == "__init__":
            return False
        if node.name in {"get_stats", "create_collector"}:
            return False
        if node.name.startswith("parse_"):
            return False
        if node.name in REQUIRED_FUNC_NAMES:
            return True
        if node.name.startswith("test_"):
            return False
        if node.name.startswith("_"):
            return False
        if len(node.body) > 8:
            return True
    return False


def check_file(path: Path) -> list[str]:
    rel = path.relative_to(ROOT)
    module = ast.parse(path.read_text(encoding="utf-8"))
    errors: list[str] = []

    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue

        if isinstance(node, ast.ClassDef):
            members = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        else:
            members = [node]

        for member in members:
            if isinstance(member, ast.ClassDef):
                continue
            doc = ast.get_docstring(member)
            label = member.name if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else f"{node.name}.{member.name}"

            if should_require_docstring(path, member) and doc is None:
                errors.append(f"{rel}:{member.lineno} missing docstring for {label}")
                continue

            if doc and doc.startswith(DISCOURAGED_PREFIXES) and not label.startswith("test_"):
                if "." in label or label.startswith("_"):
                    continue
                errors.append(f"{rel}:{member.lineno} discouraged mechanical docstring for {label}")

    return errors


def main() -> int:
    errors: list[str] = []
    for path in iter_python_files():
        errors.extend(check_file(path))

    if errors:
        print("comment policy violations:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("comment policy OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
