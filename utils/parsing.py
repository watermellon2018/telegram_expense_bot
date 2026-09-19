"""Text parsing helpers."""

import re
from typing import Dict, Optional

from utils import currencies


def parse_add_command(text: str) -> Optional[Dict[str, object]]:
    """Parse free-form expense text or `/add` command."""
    text = re.sub(r"^/add(?:@\w+)?\s+", "", text.strip())
    pattern = r"^(\d+(?:[.,]\d+)?)\s+(\w+)(?:\s+(.+))?$"
    match = re.match(pattern, text)
    if not match:
        return None

    amount = currencies.parse_amount(match.group(1))
    category = match.group(2).lower()
    description = match.group(3) if match.group(3) else ""
    currency = None
    token = match.group(2)
    if token.upper() in currencies.CURRENCIES or re.fullmatch(r"[A-Z]{3}", token):
        currency = currencies.normalize_currency(token)
        if not description:
            return None
        parts = description.split(maxsplit=1)
        category = parts[0].lower()
        description = parts[1] if len(parts) > 1 else ""
    result = {
        "amount": amount,
        "category": category,
        "description": description,
    }
    if currency:
        result["currency"] = currency
    return result
