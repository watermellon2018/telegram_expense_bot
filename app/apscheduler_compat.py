"""Compatibility patch for APScheduler timezone handling."""

import pytz
import apscheduler.util


def _patched_astimezone(obj):
    if obj is None:
        return pytz.UTC
    if hasattr(obj, "localize"):
        return obj
    return pytz.UTC


def apply_apscheduler_utc_patch() -> None:
    """Force APScheduler to use UTC-aware timezone helpers."""
    apscheduler.util.astimezone = _patched_astimezone
    apscheduler.util.get_localzone = lambda: pytz.UTC
