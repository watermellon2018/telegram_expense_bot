"""Application package.

Intentionally keeps import side effects to zero so startup patches (for example
APScheduler timezone compatibility patch) can be applied before importing other
application modules.
"""

__all__ = []
