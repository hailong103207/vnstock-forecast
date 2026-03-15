"""Utilities to link runtime with user workspace assets.

This module provides:
- Lazy loading of technique modules from core + ``user/`` directories.
- Profile directory resolution with precedence for user-owned assets.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from vnstock_forecast.engine.utils.env_utils import get_project_root

logger = logging.getLogger(__name__)

PROJECT_ROOT = get_project_root()

CORE_STRATEGIES_PACKAGE = "user.builtin.bots.technical.strategies"
DEFAULT_PROFILE_REL = "user/profiles"
PROFILE_SEARCH_REL = [
    "user/profiles",
    "user/builtin/profiles",
    "profile",
]
TECHNIQUE_SOURCE_DIRS_REL = [
    "user/bots",
]

_LOADED_CORE = False
_LOADED_USER_FILES: set[Path] = set()


@dataclass
class ModuleLoadReport:
    """Summary of module loading from user workspace."""

    loaded: list[str]
    skipped: list[str]
    failed: list[tuple[str, str]]


def _to_abs(rel_path: str) -> Path:
    return PROJECT_ROOT / rel_path


def _ensure_project_root_on_sys_path() -> None:
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _iter_python_files(base_dir: Path):
    if not base_dir.exists() or not base_dir.is_dir():
        return

    for py_file in base_dir.rglob("*.py"):
        name = py_file.name
        if name.startswith("_"):
            continue
        yield py_file


def _module_name_from_path(file_path: Path) -> str:
    rel = file_path.relative_to(PROJECT_ROOT)
    stem = "_".join(rel.with_suffix("").parts)
    return f"vnstock_user.{stem}"


def _load_module_from_file(file_path: Path) -> None:
    module_name = _module_name_from_path(file_path)
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec for {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)


def ensure_technique_modules_loaded() -> ModuleLoadReport:
    """Ensure core and user technique modules are imported exactly once.

    Returns:
        ``ModuleLoadReport`` containing loaded/skipped/failed module paths.
    """

    global _LOADED_CORE

    loaded: list[str] = []
    skipped: list[str] = []
    failed: list[tuple[str, str]] = []

    _ensure_project_root_on_sys_path()

    if not _LOADED_CORE:
        try:
            importlib.import_module(CORE_STRATEGIES_PACKAGE)
        except ModuleNotFoundError:
            logger.info(
                "Builtin strategies package not found: %s", CORE_STRATEGIES_PACKAGE
            )
        _LOADED_CORE = True

    for rel_dir in TECHNIQUE_SOURCE_DIRS_REL:
        abs_dir = _to_abs(rel_dir)
        if not abs_dir.exists():
            continue

        for file_path in _iter_python_files(abs_dir):
            if file_path in _LOADED_USER_FILES:
                skipped.append(str(file_path.relative_to(PROJECT_ROOT)))
                continue

            try:
                _load_module_from_file(file_path)
                _LOADED_USER_FILES.add(file_path)
                loaded.append(str(file_path.relative_to(PROJECT_ROOT)))
            except Exception as exc:
                failed.append((str(file_path.relative_to(PROJECT_ROOT)), str(exc)))
                logger.warning("Cannot load user module %s: %s", file_path, exc)

    return ModuleLoadReport(loaded=loaded, skipped=skipped, failed=failed)


def resolve_profile_dir(
    preferred: str | Path | None = None,
    create_if_missing: bool = False,
) -> Path:
    """Resolve profile directory with user-first precedence.

    Precedence order:
    1. ``preferred`` (if provided)
    2. ``user/profiles``
    3. ``user/builtin/profiles``
    4. legacy ``profile``

    If none exists, returns ``user/profiles`` by default.
    """

    if preferred is not None:
        path = Path(preferred)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if create_if_missing:
            path.mkdir(parents=True, exist_ok=True)
        return path

    for rel_path in PROFILE_SEARCH_REL:
        candidate = _to_abs(rel_path)
        if candidate.exists() and candidate.is_dir():
            return candidate

    default_dir = _to_abs(DEFAULT_PROFILE_REL)
    if create_if_missing:
        default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir
