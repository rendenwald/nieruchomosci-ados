"""
Cache key generation utilities.

Provides deterministic SHA-256 based cache keys from normalized query
parameters, ensuring identical filter sets produce identical keys
regardless of parameter ordering or default-value omissions.
"""

import hashlib
import json
from typing import Any


def normalize_params(params: dict[str, Any]) -> str:
    """Normalize a parameter dict into a canonical JSON string.

    Normalization steps:
        1. Sort keys alphabetically.
        2. Omit parameters with ``None`` or empty string values.
        3. Convert all values to their natural types.
        4. Serialize as compact JSON (no whitespace).

    Args:
        params: Raw query parameters dict.

    Returns:
        A canonical JSON string with sorted keys and no empty defaults.

    """
    # Filter out None and empty string values
    filtered = {
        k: v
        for k, v in params.items()
        if v is not None and v != "" and v is not ...
    }
    # Sort keys alphabetically for determinism
    return json.dumps(filtered, sort_keys=True, separators=(",", ":"))


def calculate_sha256(data: str) -> str:
    """Return the SHA-256 hex digest of a string.

    Args:
        data: The input string to hash.

    Returns:
        A 64-character lowercase hex string.

    """
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def make_cache_key(prefix: str, params: dict[str, Any]) -> str:
    """Generate a deterministic cache key from query parameters.

    Format: ``{prefix}:{sha256hex(normalized_params)}``

    Args:
        prefix: Cache key prefix (e.g. ``"properties:list:v1"``).
        params: Raw query parameters dict.

    Returns:
        A deterministic cache key string.

    """
    normalized = normalize_params(params)
    sha256hex = calculate_sha256(normalized)
    return f"{prefix}:{sha256hex}"
