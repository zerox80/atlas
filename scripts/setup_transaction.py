#!/usr/bin/env python3
"""Recoverable filesystem snapshots for the interactive proxy setup."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class _PathSnapshot:
    path: Path
    file_copy: Path | None
    symlink_target: str | None
    existed: bool


class ConfigurationSnapshot:
    """Capture selected files and symlinks and restore them on demand."""

    def __init__(self, paths: list[Path]) -> None:
        self._temporary_directory = Path(tempfile.mkdtemp(prefix="atlas-proxy-rollback-"))
        self._snapshots = [self._capture(path, index) for index, path in enumerate(paths)]

    def _capture(self, path: Path, index: int) -> _PathSnapshot:
        if path.is_symlink():
            return _PathSnapshot(path, None, os.readlink(path), True)
        if not path.exists():
            return _PathSnapshot(path, None, None, False)
        if not path.is_file():
            raise RuntimeError(f"Rollback-Pfad ist keine Datei: {path}")

        file_copy = self._temporary_directory / f"{index}.snapshot"
        shutil.copy2(path, file_copy)
        return _PathSnapshot(path, file_copy, None, True)

    def restore(self) -> list[str]:
        """Best-effort restore of every path, returning any recovery errors."""
        errors: list[str] = []
        for snapshot in reversed(self._snapshots):
            try:
                if snapshot.path.is_symlink() or snapshot.path.is_file():
                    snapshot.path.unlink()
                elif snapshot.path.exists():
                    raise RuntimeError("aktueller Pfad ist keine Datei oder Symlink")

                if not snapshot.existed:
                    continue
                snapshot.path.parent.mkdir(parents=True, exist_ok=True)
                if snapshot.symlink_target is not None:
                    snapshot.path.symlink_to(snapshot.symlink_target)
                elif snapshot.file_copy is not None:
                    shutil.copy2(snapshot.file_copy, snapshot.path)
            except Exception as error:
                errors.append(f"{snapshot.path}: {error}")
        return errors

    def close(self) -> None:
        shutil.rmtree(self._temporary_directory, ignore_errors=True)


def proxy_configuration_snapshot(
    compose: Path,
    env_file: Path,
    site: Path,
    site_link: Path,
    tls_dir: Path,
) -> ConfigurationSnapshot:
    """Capture every host file the proxy setup can replace."""
    return ConfigurationSnapshot(
        [
            compose,
            env_file,
            site,
            site_link,
            tls_dir / "atlas-local-ca.key",
            tls_dir / "atlas-local-ca.crt",
            tls_dir / "atlas-local-ca.srl",
            tls_dir / "atlas.key",
            tls_dir / "atlas.csr",
            tls_dir / "atlas.crt",
            Path("/etc/letsencrypt/renewal-hooks/deploy/reload-nginx"),
            Path("/etc/ufw/user.rules"),
            Path("/etc/ufw/user6.rules"),
        ]
    )


def recover_proxy_setup(
    snapshot: ConfigurationSnapshot,
    project: Path,
    run_command: Callable[..., None],
    reload_ufw: bool,
    setup_error: Exception,
) -> str:
    """Restore files and bring the previous runtime configuration back."""
    errors = snapshot.restore()
    commands: list[tuple[str, list[str], Path | None]] = [
        ("Nginx-Konfiguration", ["nginx", "-t"], None),
        ("Nginx-Neuladen", ["systemctl", "reload", "nginx"], None),
        (
            "Docker-Dienste",
            [
                "docker",
                "compose",
                "up",
                "-d",
                "--force-recreate",
                "backend",
                "frontend",
            ],
            project,
        ),
    ]
    if reload_ufw:
        commands.append(("UFW-Neuladen", ["ufw", "reload"], None))

    for label, args, cwd in commands:
        if shutil.which(args[0]) is None:
            continue
        try:
            run_command(args, cwd=cwd)
        except Exception as error:
            errors.append(f"{label}: {error}")
    prefix = f"Setup fehlgeschlagen ({setup_error})"
    if errors:
        return prefix + "; Rollback war unvollständig:\n" + "\n".join(
            f"- {message}" for message in errors
        )
    return prefix + "; die vorherige Konfiguration wurde wiederhergestellt."
