#!/usr/bin/env python3
"""저장소 구조·추적 파일명 기준선 검사. 서비스 기능 또는 비밀 내용 검사 아님."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    ".gitattributes",
    ".gitignore",
    ".github/workflows/baseline.yml",
    "docs/architecture.md",
    "docs/development.md",
    "docs/threat-model.md",
    "docs/demo.md",
    "docs/submission.md",
    "docs/decisions/0001-repository-layout.md",
    "apps/policy-server/README.md",
    "apps/dns-agent/README.md",
    "apps/warning-portal/README.md",
    "packages/policy-contract/README.md",
)

REQUIRED_DIRS = (
    "apps/policy-server/src/policy_server/intel",
    "apps/policy-server/src/policy_server/review",
    "apps/policy-server/src/policy_server/publisher",
    "apps/policy-server/src/policy_server/api",
    "apps/policy-server/tests",
    "apps/dns-agent/src/dns_agent",
    "apps/dns-agent/resolver",
    "apps/dns-agent/tests",
    "apps/warning-portal/src",
    "apps/warning-portal/tests",
    "packages/policy-contract/schema",
    "packages/policy-contract/examples",
    "packages/policy-contract/test-vectors",
    "infra/lab",
    "infra/edge",
    "infra/server",
    "tests/e2e",
)

PRIVATE_DIRS = {"secrets", "private", "credentials", "runtime", "inbox"}
PRIVATE_SUFFIXES = {
    ".key", ".pem", ".p12", ".pfx", ".crt", ".kdbx", ".ovpn",
    ".db", ".sqlite", ".sqlite3", ".pcap", ".pcapng", ".tfvars",
}


def tracked_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("git ls-files 실패: Git 체크아웃 안에서 실행해야 합니다")
    return [Path(p.decode("utf-8")) for p in result.stdout.split(b"\0") if p]


def main() -> int:
    errors: list[str] = []
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            errors.append(f"필수 파일 누락: {rel}")
    for rel in REQUIRED_DIRS:
        if not (ROOT / rel).is_dir():
            errors.append(f"필수 디렉터리 누락: {rel}")

    try:
        tracked = tracked_paths()
    except RuntimeError as exc:
        errors.append(str(exc))
        tracked = []

    for path in tracked:
        name = path.name.lower()
        parts = set(part.lower() for part in path.parts)
        if (parts & PRIVATE_DIRS) or (name.startswith(".env") and name != ".env.example"):
            errors.append(f"민감한 경로가 Git 추적됨: {path}")
        if (
            path.suffix.lower() in PRIVATE_SUFFIXES
            or name.endswith(".tfstate")
            or ".tfstate." in name
            or name.startswith("terraform.tfstate")
        ):
            errors.append(f"금지 파일 확장자/이름: {path}")
        if (ROOT / path).is_symlink():
            errors.append(f"심볼릭 링크는 별도 검토 필요: {path}")

        if (
            path.suffix.lower() == ".json"
            and path.parts[:2] == ("packages", "policy-contract")
        ):
            try:
                json.loads((ROOT / path).read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
                errors.append(f"정책 JSON 구문 오류: {path}: {exc}")

    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print(
        f"Baseline OK ({len(tracked)} tracked files): structure and filename checks only."
    )
    print("DNS/HTTPS behavior, credential values, and application tests: NOT VERIFIED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
