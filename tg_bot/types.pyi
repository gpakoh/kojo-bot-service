"""Project type stubs for telegram.ext.CallbackContext."""
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


def __getattr__(name: str) -> Any:
    if name == "di":
        from tg_bot.di.provider import Container
        return Container
    raise AttributeError(f"module {name!r} has no attribute {name!r}")
