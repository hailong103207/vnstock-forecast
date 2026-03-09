"""Registry – đăng ký và tra cứu technique bằng decorator."""

from __future__ import annotations

from typing import Callable, Type

from .base import BaseTechnique

# Global registry: name → technique class
_REGISTRY: dict[str, Type[BaseTechnique]] = {}


def register(name: str) -> Callable[[Type[BaseTechnique]], Type[BaseTechnique]]:
    """
    Decorator đăng ký technique class vào global registry.

    Usage::

        @register("rsi_crossover")
        class RSICrossover(BaseTechnique):
            ...

    Sau đó có thể tìm lại bằng ``get_technique("rsi_crossover")``.
    """

    def decorator(cls: Type[BaseTechnique]) -> Type[BaseTechnique]:
        if name in _REGISTRY:
            raise ValueError(
                f"Technique '{name}' đã được đăng ký bởi {_REGISTRY[name].__name__}. "
                f"Không thể đăng ký {cls.__name__} cùng tên."
            )
        if not issubclass(cls, BaseTechnique):
            raise TypeError(f"{cls.__name__} phải kế thừa BaseTechnique để đăng ký.")
        _REGISTRY[name] = cls
        # Gắn tên registry vào class nếu chưa có custom name
        if cls.name == "BaseTechnique":
            cls.name = name
        return cls

    return decorator


def get_technique(name: str) -> Type[BaseTechnique]:
    """
    Tìm technique class theo tên đã đăng ký.

    Args:
        name: Tên technique (trùng với tham số trong ``@register(name)``).

    Returns:
        Class (chưa khởi tạo). Gọi ``cls()`` để tạo instance.

    Raises:
        KeyError: Không tìm thấy technique.
    """
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys())) or "(trống)"
        raise KeyError(f"Technique '{name}' chưa đăng ký. Có sẵn: {available}")
    return _REGISTRY[name]


def get_all_techniques() -> dict[str, Type[BaseTechnique]]:
    """Trả về dict tất cả technique đã đăng ký: ``{name: class}``."""
    return dict(_REGISTRY)


def list_technique_names() -> list[str]:
    """Trả về danh sách tên tất cả technique đã đăng ký."""
    return sorted(_REGISTRY.keys())


def clear_registry() -> None:
    """Xóa toàn bộ registry. Chỉ dùng cho testing."""
    _REGISTRY.clear()
