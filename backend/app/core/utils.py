"""TraceHeal Core Utilities.

Safe parsing, serialization, and defensive helpers.
"""

import json
from typing import Any, Optional


def safe_json_loads(data: Any, fallback: Any = None) -> Any:
    """Safely parses JSON strings, returning fallback if None, invalid, or already parsed."""
    if data is None:
        return fallback if fallback is not None else {}
    if isinstance(data, (dict, list)):
        return data
    if isinstance(data, (bytes, bytearray)):
        try:
            data = data.decode("utf-8")
        except Exception:
            return fallback if fallback is not None else {}
    if isinstance(data, str):
        cleaned = data.strip()
        if not cleaned:
            return fallback if fallback is not None else {}
        try:
            return json.loads(cleaned)
        except Exception:
            return fallback if fallback is not None else {}
    return fallback if fallback is not None else {}


def safe_json_dumps(data: Any, fallback: str = "{}") -> str:
    """Safely serializes an object to JSON string, returning fallback on serialization error."""
    if data is None:
        return fallback
    if isinstance(data, str):
        return data
    try:
        return json.dumps(data)
    except Exception:
        return fallback
