"""
Tests for cache key generation utilities.

Covers:
- Deterministic key generation for identical params regardless of ordering
- Normalization omits empty defaults
- SHA-256 output format
"""

from app.services.cache_key import calculate_sha256, make_cache_key, normalize_params


def test_normalize_params_sorts_keys() -> None:
    """Normalization produces identical output for different param orderings."""
    params_a = {"page": 1, "city": "Warszawa"}
    params_b = {"city": "Warszawa", "page": 1}

    result_a = normalize_params(params_a)
    result_b = normalize_params(params_b)

    assert result_a == result_b
    assert '"city"' in result_a
    assert '"page"' in result_a


def test_normalize_params_omits_none() -> None:
    """None values are omitted from the normalized output."""
    params = {"city": "Warszawa", "price_min": None, "page": 1, "limit": 20}
    result = normalize_params(params)
    assert '"price_min"' not in result
    assert '"city"' in result


def test_normalize_params_omits_empty_string() -> None:
    """Empty string values are omitted from the normalized output."""
    params = {"city": "", "page": 1}
    result = normalize_params(params)
    assert '"city"' not in result


def test_normalize_params_compact_json() -> None:
    """Normalized output is compact JSON (no whitespace)."""
    params = {"city": "Warszawa", "page": 1}
    result = normalize_params(params)
    # No spaces after separators
    assert " " not in result


def test_calculate_sha256_hex_length() -> None:
    """SHA-256 hex digest is 64 characters long."""
    result = calculate_sha256("test data")
    assert len(result) == 64


def test_calculate_sha256_hex_chars() -> None:
    """SHA-256 hex digest contains only lowercase hex chars."""
    result = calculate_sha256("test data")
    assert all(c in "0123456789abcdef" for c in result)


def test_calculate_sha256_deterministic() -> None:
    """Same input produces same hash."""
    a = calculate_sha256("hello")
    b = calculate_sha256("hello")
    assert a == b


def test_calculate_sha256_different() -> None:
    """Different inputs produce different hashes."""
    a = calculate_sha256("hello")
    b = calculate_sha256("world")
    assert a != b


def test_make_cache_key_format() -> None:
    """Cache key matches ``prefix:sha256hex`` format."""
    key = make_cache_key("properties:list:v1", {"city": "Warszawa", "page": 1})
    assert key.startswith("properties:list:v1:")
    # After prefix and colon, there should be 64 hex chars
    sha256_part = key.split(":")[-1]
    assert len(sha256_part) == 64
    assert all(c in "0123456789abcdef" for c in sha256_part)


def test_make_cache_key_deterministic() -> None:
    """Same params produce same cache key regardless of ordering."""
    key_a = make_cache_key("p", {"page": 1, "city": "Warszawa"})
    key_b = make_cache_key("p", {"city": "Warszawa", "page": 1})
    assert key_a == key_b


def test_make_cache_key_different_params_different_key() -> None:
    """Different params produce different cache keys."""
    key_a = make_cache_key("p", {"city": "Warszawa"})
    key_b = make_cache_key("p", {"city": "Kraków"})
    assert key_a != key_b
