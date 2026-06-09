"""Text parsing helpers."""

import re
from typing import Dict, Optional


def parse_add_command(text: str) -> Optional[Dict[str, object]]:
    """Parse free-form expense text or `/add` command."""
    if text.startswith("/add "):
        text = text[5:].strip()

    pattern = r"^(\d+(?:\.\d+)?)\s+(\w+)(?:\s+(.+))?$"
    match = re.match(pattern, text)
    if not match:
        return None

    amount = float(match.group(1))
    category = match.group(2).lower()
    description = match.group(3) if match.group(3) else ""
    return {
        "amount": amount,
        "category": category,
        "description": description,
    }
