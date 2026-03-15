"""Compatibility layer cho bot examples ở user-space.

Nguồn chính của bot mẫu nằm tại ``user/bots/examples/examples.py``.
Module này được giữ lại để không làm vỡ import cũ:

    from vnstock_forecast.engine.backtest.examples import SMABot, BuyAndHoldBot
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_user_examples_module():
    project_root = Path(__file__).resolve().parents[4]
    user_examples_path = project_root / "user" / "bots" / "examples" / "examples.py"

    if not user_examples_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file bot mẫu user-space: {user_examples_path}"
        )

    spec = spec_from_file_location("_user_bot_examples", user_examples_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Không thể load module từ {user_examples_path}")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_user_examples = _load_user_examples_module()

SMABot = _user_examples.SMABot
BuyAndHoldBot = _user_examples.BuyAndHoldBot

__all__ = ["SMABot", "BuyAndHoldBot"]
