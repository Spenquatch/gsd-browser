#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import re
import sys
from dataclasses import dataclass
from pathlib import Path


FORBIDDEN_SUBSTRINGS = ("secret", "password", "token")
FORBIDDEN_SEGMENTS = ("key",)

# Known-benign output names/patterns that include "key" but aren't secrets in this repo.
# Keep this list small and explicit; expand only with strong justification.
EXACT_ALLOWLIST = {
    "accesskeyid",
}
REGEX_ALLOWLIST = [
    # e.g. keyVaultName, keyVaultId, keyVaultUri (resource identifiers, not secrets)
    re.compile(r"keyvault", re.IGNORECASE),
    # public keys are fine to output
    re.compile(r"publickey", re.IGNORECASE),
]


OUTPUT_DECL_RE = re.compile(r"^\s*output\s+([a-zA-Z_][a-zA-Z0-9_]*)\b")
IDENT_PART_RE = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[0-9]+",
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    output_name: str
    reason: str


def _split_identifier(name: str) -> list[str]:
    # Covers camelCase, PascalCase, ALLCAPS, snake_case, and mixed digits.
    parts: list[str] = []
    for chunk in re.split(r"[_\-\s]+", name):
        if not chunk:
            continue
        parts.extend([m.group(0).lower() for m in IDENT_PART_RE.finditer(chunk)])
    return [p for p in parts if p]


def _is_allowlisted(output_name: str) -> bool:
    lower = output_name.lower()
    if lower in EXACT_ALLOWLIST:
        return True
    return any(rx.search(output_name) for rx in REGEX_ALLOWLIST)


def _classify_secretish(output_name: str) -> str | None:
    if _is_allowlisted(output_name):
        return None

    lower = output_name.lower()
    for s in FORBIDDEN_SUBSTRINGS:
        if s in lower:
            return f"contains substring '{s}'"

    segments = _split_identifier(output_name)
    for idx, seg in enumerate(segments):
        if seg in FORBIDDEN_SEGMENTS:
            # keyVault* is allowlisted above; this is an extra safety net for tokenization.
            if seg == "key" and idx + 1 < len(segments) and segments[idx + 1] == "vault":
                continue
            return "contains segment 'key'"

    return None


def _expand_paths(patterns: list[str]) -> list[Path]:
    out: set[Path] = set()
    for pattern in patterns:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            out.update(Path(m) for m in matches)
        else:
            p = Path(pattern)
            if p.exists():
                out.add(p)
    return sorted(out)


def scan_files(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            findings.append(
                Finding(path=path, line=0, output_name="<unreadable>", reason=f"read failed: {e}")
            )
            continue

        for i, line in enumerate(text.splitlines(), start=1):
            m = OUTPUT_DECL_RE.match(line)
            if not m:
                continue
            name = m.group(1)
            reason = _classify_secretish(name)
            if reason is None:
                continue
            findings.append(Finding(path=path, line=i, output_name=name, reason=reason))
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="CI guard: fail if infra/modules/*.bicep declares secret-ish outputs.",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Files/globs to scan (default: infra/modules/*.bicep).",
    )
    args = parser.parse_args(argv)

    patterns = args.paths if args.paths else ["infra/modules/*.bicep"]
    paths = _expand_paths(patterns)
    if not paths:
        print(f"No files matched: {patterns!r}", file=sys.stderr)
        return 2

    findings = scan_files(paths)
    violations = [f for f in findings if f.output_name != "<unreadable>"]
    unreadable = [f for f in findings if f.output_name == "<unreadable>"]

    if unreadable:
        print("Warning: some files could not be read:", file=sys.stderr)
        for f in unreadable:
            print(f"  - {f.path}: {f.reason}", file=sys.stderr)

    if not violations:
        return 0

    print("Secret-ish Bicep outputs are not allowed. Rename/remove these outputs:", file=sys.stderr)
    for f in violations:
        print(f"  - {f.path}:{f.line}: output {f.output_name} ({f.reason})", file=sys.stderr)
    print(
        "\nIf this is a false positive, add a narrow allowlist rule in "
        "infra/scripts/guard_no_secret_outputs.py.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
