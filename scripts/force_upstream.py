#!/usr/bin/env python3
"""Replace the local server checkout with origin/main without touching runtime data."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REMOTE = "origin"
BRANCH = "main"
PROTECTED_PATHS = (".env", "data", "backend/uploads")


def fail(message: str) -> None:
    print(f"Abbruch: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(
    arguments: list[str],
    repository: Path,
    *,
    capture_output: bool = False,
) -> str:
    print(f"→ {' '.join(arguments)}")
    completed = subprocess.run(
        arguments,
        cwd=repository,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture_output else None,
    )
    return completed.stdout.strip() if completed.stdout else ""


def discover_repository() -> Path:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as error:
        fail(f"Git-Repository konnte nicht gefunden werden ({error}).")
    return Path(completed.stdout.strip()).resolve()


def ensure_server_checkout(repository: Path) -> None:
    try:
        branch = run(
            ["git", "branch", "--show-current"],
            repository,
            capture_output=True,
        )
    except subprocess.CalledProcessError as error:
        fail(f"Git-Repository konnte nicht gelesen werden ({error}).")

    if branch != BRANCH:
        fail(
            f"Aktiver Branch ist '{branch or 'detached'}', "
            f"erwartet wird '{BRANCH}'."
        )

    tracked_runtime_files = run(
        ["git", "ls-files", "--", *PROTECTED_PATHS],
        repository,
        capture_output=True,
    )
    if tracked_runtime_files:
        fail(
            "Geschützte Laufzeitdaten sind unerwartet versioniert:\n"
            f"{tracked_runtime_files}"
        )


def ensure_target_does_not_track_runtime_data(
    repository: Path, target: str
) -> None:
    tracked_runtime_files = run(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            target,
            "--",
            *PROTECTED_PATHS,
        ],
        repository,
        capture_output=True,
    )
    if tracked_runtime_files:
        fail(
            f"{target} enthält unerwartet geschützte Laufzeitdaten:\n"
            f"{tracked_runtime_files}"
        )


def main() -> None:
    repository = discover_repository()
    ensure_server_checkout(repository)

    target = f"{REMOTE}/{BRANCH}"
    print(
        "Lokale Code-Änderungen werden jetzt ohne Backup verworfen.\n"
        "Erhalten bleiben: .env, data/ und backend/uploads/."
    )

    try:
        run(["git", "fetch", REMOTE], repository)
        ensure_target_does_not_track_runtime_data(repository, target)
        run(["git", "reset", "--hard", target], repository)
        run(
            [
                "git",
                "clean",
                "-fd",
                "-e",
                ".env",
                "-e",
                "data/",
                "-e",
                "backend/uploads/",
            ],
            repository,
        )
    except subprocess.CalledProcessError as error:
        fail(f"Upstream-Reset fehlgeschlagen ({error}).")

    print(f"Fertig: Der lokale Code entspricht {target}.")


if __name__ == "__main__":
    main()
