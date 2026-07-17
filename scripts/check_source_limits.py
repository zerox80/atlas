#!/usr/bin/env python3
"""Enforce the repository-wide source file length limit."""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


MAX_FILE_LINES = 500

SOURCE_SUFFIXES = {
    ".cjs",
    ".css",
    ".cts",
    ".js",
    ".jsx",
    ".mjs",
    ".mts",
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
}

IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
}


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    kind: str
    actual: int
    limit: int

    @property
    def title(self) -> str:
        if self.kind == "file-lines":
            return "File too long"
        return "Invalid source encoding"

    @property
    def message(self) -> str:
        if self.kind == "file-lines":
            return f"File has {self.actual} lines; maximum allowed is {self.limit}."
        return "File is not valid UTF-8."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to scan (defaults to the parent of the scripts directory).",
    )
    return parser.parse_args()


def source_files(root: Path) -> list[Path]:
    files = []
    for current_directory, directory_names, file_names in os.walk(root):
        directory_names[:] = sorted(
            name for name in directory_names if name.lower() not in IGNORED_DIRECTORIES
        )
        directory = Path(current_directory)
        for file_name in sorted(file_names):
            path = directory / file_name
            if path.suffix.lower() in SOURCE_SUFFIXES:
                files.append(path)
    return sorted(files)


def inspect_file(path: Path, root: Path) -> list[Violation]:
    relative_path = path.relative_to(root).as_posix()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as error:
        print(f"{relative_path}: could not be decoded as UTF-8: {error}", file=sys.stderr)
        return [Violation(relative_path, 1, "encoding", 1, 0)]

    violations = []
    if len(lines) > MAX_FILE_LINES:
        violations.append(
            Violation(relative_path, MAX_FILE_LINES + 1, "file-lines", len(lines), MAX_FILE_LINES)
        )

    return violations


def escape_workflow_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_workflow_property(value: str) -> str:
    return escape_workflow_data(value).replace(":", "%3A").replace(",", "%2C")


def emit_annotation(violation: Violation) -> None:
    print(f"{violation.path}:{violation.line}: error: {violation.message}")
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return

    path = escape_workflow_property(violation.path)
    title = escape_workflow_property(violation.title)
    message = escape_workflow_data(violation.message)
    print(f"::error file={path},line={violation.line},title={title}::{message}")


def write_step_summary(files_checked: int, violations: list[Violation]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    if violations:
        heading = "# Source limits failed"
        outcome = f"Found **{len(violations)} violation(s)** in {files_checked} checked source files."
    else:
        heading = "# Source limits passed"
        outcome = f"All {files_checked} checked source files are within the configured limits."

    lines = [
        heading,
        "",
        outcome,
        "",
        f"- Maximum file length: **{MAX_FILE_LINES} lines**",
    ]

    if violations:
        lines.extend(["", "| File | Line | Reason |", "| --- | ---: | --- |"])
        for violation in violations:
            safe_path = violation.path.replace("|", "\\|")
            safe_message = violation.message.replace("|", "\\|")
            lines.append(f"| `{safe_path}` | {violation.line} | {safe_message} |")

    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write("\n".join(lines) + "\n")


def main() -> int:
    root = parse_args().root.resolve()
    files = source_files(root)
    violations = [violation for path in files for violation in inspect_file(path, root)]

    for violation in violations:
        emit_annotation(violation)

    write_step_summary(len(files), violations)

    if violations:
        counts = Counter(violation.kind for violation in violations)
        print(
            "Source limit check failed: "
            f"{counts['file-lines']} oversized file(s), "
            f"{counts['encoding']} encoding error(s).",
            file=sys.stderr,
        )
        return 1

    print(f"Source limit check passed for {len(files)} files (maximum {MAX_FILE_LINES} lines per file).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
