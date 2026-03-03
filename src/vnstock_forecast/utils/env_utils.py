from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def load_environment_variables(filename: str = ".env", override: bool = False):
    """
    Automatically load environment variables from a .env file.
    Args:
        filename (str): The name of the .env file to load. Defaults to ".env"
        o
    Raises:
        FileNotFoundError: If the specified .env file is not found.
    """
    env_path = find_dotenv(filename, usecwd=True)
    if env_path:
        load_dotenv(env_path, override=override)
    else:
        raise FileNotFoundError(f"{filename} file not found.")


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
