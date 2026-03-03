from pathlib import Path
from typing import List, Optional

import hydra
from hydra.core.global_hydra import GlobalHydra
from omegaconf import DictConfig, OmegaConf


def get_project_root() -> Path:
    """
    Get the root directory of the project by looking for marker files.

    Tries to find the project root by looking for (in order):
    1. pyproject.toml (modern Python projects)
    2. .git (git-based projects)
    3. setup.py (legacy Python projects)
    4. .env (dotenv file)

    If no marker is found, returns the current working directory.

    Returns:
        Path: The root directory of the project.
    """
    # List of marker files/folders that indicate project root
    markers = ["pyproject.toml", ".git", "setup.py", ".env"]

    # Start from current working directory
    current = Path.cwd()

    # Traverse up the directory tree
    for parent in [current] + list(current.parents):
        for marker in markers:
            if (parent / marker).exists():
                return parent

    # Fallback to current working directory if no marker found
    return current


def load_config(
    config_name: str = "config",
    overrides: Optional[List[str]] = None,
    resolve: bool = True,
) -> DictConfig:
    """
    Load Hydra Config (for Notebooks & Tests).

    Args:
        config_name: Config file name (default is "config").
        overrides: List of parameters to override (e.g., ["training.epochs=10"]).
        resolve: If True, resolve all interpolations (e.g. ${...}) into actual values.

    Returns:
        DictConfig: The merged config object.
    """
    # 1. Clear old Hydra instance (Important when re-running cells in Notebooks)
    GlobalHydra.instance().clear()

    # 2. Get config path dynamically (no package import dependency)
    config_dir = str(get_project_root() / "config")

    # 3. Initialize and Compose
    with hydra.initialize_config_dir(version_base=None, config_dir=config_dir):
        cfg = hydra.compose(
            config_name=config_name, overrides=overrides if overrides else []
        )

    # 4. Optionally resolve all interpolations
    if resolve:
        cfg = OmegaConf.create(OmegaConf.to_container(cfg, resolve=True))

    return cfg


def print_config(cfg: DictConfig, resolve: bool = True):
    """Helper to print config in a readable format"""
    print(OmegaConf.to_yaml(cfg, resolve=resolve))


if __name__ == "__main__":
    # Example usage
    config = load_config(
        config_name="config",
    )
    print_config(config)
