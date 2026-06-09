"""Public handler registration entrypoint (backward compatible)."""

from handlers.registry import register_all_handlers

__all__ = ["register_all_handlers"]
