"""Assetto Corsa installation discovery on supported desktop operating systems."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Mapping


def assetto_corsa_root_candidates(
    *,
    platform_name: str | None = None,
    home: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    platform_name = platform_name or sys.platform
    home = home or Path.home()
    environment = os.environ if environment is None else environment
    suffix = Path("steamapps") / "common" / "assettocorsa"

    if platform_name == "win32":
        roots = [
            Path(value) / "Steam" / suffix
            for value in (environment.get("PROGRAMFILES(X86)"), environment.get("PROGRAMFILES"))
            if value
        ]
    elif platform_name == "darwin":
        roots = [home / "Library" / "Application Support" / "Steam" / suffix]
    else:
        roots = [
            home / ".local" / "share" / "Steam" / suffix,
            home / ".steam" / "steam" / suffix,
        ]

    return tuple(dict.fromkeys(roots))


def _existing_root() -> Path | None:
    return next(
        (path for path in assetto_corsa_root_candidates() if path.is_dir()),
        None,
    )


def default_snapshot_path() -> Path | None:
    root = _existing_root()
    path = root / "apps" / "python" / "TReS" / "telemetry.json" if root else None
    return path if path is not None and path.parent.is_dir() else None


def default_tracks_root() -> Path | None:
    root = _existing_root()
    path = root / "content" / "tracks" if root else None
    return path if path is not None and path.is_dir() else None
