"""
Project-level config helpers.

This module owns every concern that is specific to this project's layout:
- locating the ``config/data/discovery/symbols`` folder
- scanning symbol YAML files (``discover_symbols``)
- registering the ``${symbols:key}`` OmegaConf resolver
- providing a project-aware ``load_config`` / ``load_app_config``

Generic, project-agnostic Hydra/OmegaConf utilities live in
``vnstock_forecast.utils.config_utils``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from omegaconf import DictConfig, OmegaConf, open_dict

import vnstock_forecast.schemas.config  # noqa: F401 — registers AppConfig dataclass
from vnstock_forecast.utils.config_utils import get_project_root
from vnstock_forecast.utils.config_utils import load_config as _load_config_generic
from vnstock_forecast.utils.config_utils import print_config

__all__ = [
    "discover_symbols",
    "load_config",
    "print_config",
]

# ---------------------------------------------------------------------------
# Symbol discovery
# ---------------------------------------------------------------------------

_SYMBOLS_DIR = "config/data/discovery/symbols"


def discover_symbols(symbols_dir: Path) -> Dict[str, Any]:
    """
    Recursively scan *symbols_dir* for ``*.yaml`` files and return a dict
    keyed by the file stem (lower-cased).

    Layout example::

        symbols/
            VN30.yaml           → key "vn30"
            STEEL/
                STEEL_L4.yaml   → key "steel_l4"

    Returns:
        dict[str, list[str]]
    """
    result: Dict[str, Any] = {}
    for yaml_file in sorted(symbols_dir.rglob("*.yaml")):
        key = yaml_file.stem.lower()
        result[key] = yaml.safe_load(yaml_file.read_text()) or []
    return result


# ---------------------------------------------------------------------------
# OmegaConf resolver  ${symbols:vn30}
# ---------------------------------------------------------------------------


def _symbols_resolver(key: str) -> List[str]:
    symbols_dir = get_project_root() / _SYMBOLS_DIR
    return discover_symbols(symbols_dir).get(key.lower(), [])


# Registered once on first import of this module — works for both
# load_config() and @hydra.main without any further setup.
OmegaConf.register_new_resolver("symbols", _symbols_resolver, replace=True)


# ---------------------------------------------------------------------------
# Project-aware config loader
# ---------------------------------------------------------------------------


def load_config(
    config_name: str = "config",
    overrides: Optional[List[str]] = None,
    resolve: bool = True,
) -> DictConfig:
    """Load Hydra config and inject all discovered symbol sets."""
    cfg = _load_config_generic(
        config_name=config_name, overrides=overrides, resolve=False
    )

    symbols_dir = get_project_root() / _SYMBOLS_DIR
    if symbols_dir.exists():
        with open_dict(cfg):
            cfg.data.discovery.symbols = OmegaConf.create(discover_symbols(symbols_dir))

    if resolve:
        OmegaConf.resolve(cfg)

    return cfg
