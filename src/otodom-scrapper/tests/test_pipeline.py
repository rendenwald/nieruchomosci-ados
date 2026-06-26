"""Tests for ``OtodomPipeline.item_to_data()`` normalization.

Test cases cover all field transformations: price, area, photos,
JSONB defaults, and portal_source assignment.
"""

from __future__ import annotations

from typing import Any

from otodom_scrapper.pipelines import OtodomPipeline


def _run(item: dict[str, Any], pipeline: OtodomPipeline) -> dict[str, Any]:
    """Helper: run ``item_to_data`` and return the result."""
    return pipeline.item_to_data(item)


# ── Portal source ────────────────────────────────────────────────────────


class TestPortalSource:
    """Verify portal_source is always set to 'otodom'."""

    def test_portal_source_default(self, pipeline: OtodomPipeline) -> None:
        """TC-P18: Empty item gets portal_source='otodom'."""
        result = _run({}, pipeline)
        assert result["portal_source"] == "otodom"

    def test_portal_source_overwrite(self, pipeline: OtodomPipeline) -> None:
        """Setting portal_source to something else is overridden."""
        result = _run({"portal_source": "gratka"}, pipeline)
        assert result["portal_source"] == "otodom"


# ── Price normalization ──────────────────────────────────────────────────


class TestPriceNormalization:
    """AC-4: Price strings normalized to integers."""

    def test_price_zloty_suffix(self, pipeline: OtodomPipeline) -> None:
        """TC-P1: '520 000 zł' → 520000."""
        result = _run({"price": "520 000 z\u0142"}, pipeline)
        assert result["price"] == 520000

    def test_price_pln_suffix(self, pipeline: OtodomPipeline) -> None:
        """TC-P2: '350000 PLN' → 350000."""
        result = _run({"price": "350000 PLN"}, pipeline)
        assert result["price"] == 350000

    def test_price_integer(self, pipeline: OtodomPipeline) -> None:
        """TC-P3: 750000 (int) → 750000."""
        result = _run({"price": 750000}, pipeline)
        assert result["price"] == 750000

    def test_price_invalid(self, pipeline: OtodomPipeline) -> None:
        """TC-P4: 'NEGOTIABLE' → None."""
        result = _run({"price": "NEGOTIABLE"}, pipeline)
        assert result["price"] is None

    def test_price_none(self, pipeline: OtodomPipeline) -> None:
        """None price stays None."""
        result = _run({"price": None}, pipeline)
        assert result["price"] is None

    def test_price_empty_string(self, pipeline: OtodomPipeline) -> None:
        """Empty string price stays None."""
        result = _run({"price": ""}, pipeline)
        assert result["price"] is None


# ── Price per m² normalization ──────────────────────────────────────────


class TestPricePerM2Normalization:
    """AC-4: Price per m² strings normalized to integers."""

    def test_price_per_m2_full(self, pipeline: OtodomPipeline) -> None:
        """TC-P12: '8 500 zł/m²' → 8500."""
        result = _run({"price_per_m2": "8 500 z\u0142/m\u00b2"}, pipeline)
        assert result["price_per_m2"] == 8500

    def test_price_per_m2_pln_m2(self, pipeline: OtodomPipeline) -> None:
        """'9500 PLN/m2' → 9500."""
        result = _run({"price_per_m2": "9 500 PLN/m2"}, pipeline)
        assert result["price_per_m2"] == 9500

    def test_price_per_m2_invalid(self, pipeline: OtodomPipeline) -> None:
        """Invalid string → None."""
        result = _run({"price_per_m2": "Zapytaj"}, pipeline)
        assert result["price_per_m2"] is None


# ── Area normalization ───────────────────────────────────────────────────


class TestAreaNormalization:
    """AC-5: Area strings normalized to floats."""

    def test_area_m2_suffix_comma(self, pipeline: OtodomPipeline) -> None:
        """TC-P5: '58,5 m²' → 58.5."""
        result = _run({"area": "58,5 m\u00b2"}, pipeline)
        assert result["area"] == 58.5

    def test_area_m2_suffix_dot(self, pipeline: OtodomPipeline) -> None:
        """TC-P6: '72 m2' → 72.0."""
        result = _run({"area": "72 m2"}, pipeline)
        assert result["area"] == 72.0

    def test_area_no_suffix(self, pipeline: OtodomPipeline) -> None:
        """TC-P7: '45' → 45.0."""
        result = _run({"area": "45"}, pipeline)
        assert result["area"] == 45.0

    def test_area_decimal_comma(self, pipeline: OtodomPipeline) -> None:
        """'65,5' → 65.5 (comma as decimal separator)."""
        result = _run({"area": "65,5"}, pipeline)
        assert result["area"] == 65.5

    def test_area_decimal_dot(self, pipeline: OtodomPipeline) -> None:
        """'65.5' → 65.5."""
        result = _run({"area": "65.5"}, pipeline)
        assert result["area"] == 65.5

    def test_area_invalid(self, pipeline: OtodomPipeline) -> None:
        """TC-P8: 'Ask agent' → None."""
        result = _run({"area": "Ask agent"}, pipeline)
        assert result["area"] is None

    def test_area_none(self, pipeline: OtodomPipeline) -> None:
        """None stays None."""
        result = _run({"area": None}, pipeline)
        assert result["area"] is None


# ── Plot area normalization ──────────────────────────────────────────────


class TestPlotAreaNormalization:
    """AC-5: Plot area strings normalized to floats."""

    def test_plot_area_m2(self, pipeline: OtodomPipeline) -> None:
        """TC-P19: '500 m2' → 500.0."""
        result = _run({"plot_area": "500 m2"}, pipeline)
        assert result["plot_area"] == 500.0

    def test_plot_area_comma(self, pipeline: OtodomPipeline) -> None:
        """'1 200,5 m²' → 1200.5."""
        result = _run({"plot_area": "1 200,5 m\u00b2"}, pipeline)
        assert result["plot_area"] == 1200.5

    def test_plot_area_invalid(self, pipeline: OtodomPipeline) -> None:
        """Invalid → None."""
        result = _run({"plot_area": "unknown"}, pipeline)
        assert result["plot_area"] is None


# ── Photo normalization ──────────────────────────────────────────────────


class TestPhotoNormalization:
    """AC-6: Photo URLs filtered and deduplicated."""

    def test_photo_list(self, pipeline: OtodomPipeline) -> None:
        """TC-P9: Valid URLs preserved."""
        result = _run(
            {"photos": ["http://a.jpg", "http://b.jpg"]},
            pipeline,
        )
        assert result["photos"] == ["http://a.jpg", "http://b.jpg"]

    def test_photo_mixed_valid_invalid(self, pipeline: OtodomPipeline) -> None:
        """TC-P10: Invalid URLs filtered out."""
        result = _run(
            {"photos": ["http://a.jpg", "", "not-a-url"]},
            pipeline,
        )
        assert result["photos"] == ["http://a.jpg"]

    def test_photo_empty(self, pipeline: OtodomPipeline) -> None:
        """TC-P11: None → []."""
        result = _run({"photos": None}, pipeline)
        assert result["photos"] == []

    def test_photo_single_string(self, pipeline: OtodomPipeline) -> None:
        """Single URL string is converted to list."""
        result = _run({"photos": "http://a.jpg"}, pipeline)
        assert result["photos"] == ["http://a.jpg"]

    def test_photo_https(self, pipeline: OtodomPipeline) -> None:
        """HTTPS URLs preserved."""
        result = _run({"photos": ["https://a.jpg"]}, pipeline)
        assert result["photos"] == ["https://a.jpg"]

    def test_photo_non_http_filtered(self, pipeline: OtodomPipeline) -> None:
        """Non-HTTP URLs filtered."""
        result = _run(
            {"photos": ["ftp://a.jpg", "data:image/png;base64,abc"]},
            pipeline,
        )
        assert result["photos"] == []

    def test_photo_empty_list(self, pipeline: OtodomPipeline) -> None:
        """Empty list stays empty."""
        result = _run({"photos": []}, pipeline)
        assert result["photos"] == []


# ── Rooms normalization ──────────────────────────────────────────────────


class TestRoomsNormalization:
    """Rooms normalized to stripped strings."""

    def test_rooms_whitespace(self, pipeline: OtodomPipeline) -> None:
        """TC-P13: ' 3 ' → '3'."""
        result = _run({"rooms": " 3 "}, pipeline)
        assert result["rooms"] == "3"

    def test_rooms_fractional(self, pipeline: OtodomPipeline) -> None:
        """TC-P14: '3.5' → '3.5'."""
        result = _run({"rooms": "3.5"}, pipeline)
        assert result["rooms"] == "3.5"

    def test_rooms_plus(self, pipeline: OtodomPipeline) -> None:
        """'4+' → '4+'."""
        result = _run({"rooms": "4+"}, pipeline)
        assert result["rooms"] == "4+"

    def test_rooms_none(self, pipeline: OtodomPipeline) -> None:
        """None stays None."""
        result = _run({"rooms": None}, pipeline)
        assert "rooms" not in result or result.get("rooms") is None


# ── Floors total normalization ───────────────────────────────────────────


class TestFloorsTotalNormalization:
    """TC-P15: floors_total normalized to int."""

    def test_floors_total_string(self, pipeline: OtodomPipeline) -> None:
        """'12' → 12."""
        result = _run({"floors_total": "12"}, pipeline)
        assert result["floors_total"] == 12

    def test_floors_total_int(self, pipeline: OtodomPipeline) -> None:
        """12 → 12."""
        result = _run({"floors_total": 12}, pipeline)
        assert result["floors_total"] == 12

    def test_floors_total_invalid(self, pipeline: OtodomPipeline) -> None:
        """Invalid → None."""
        result = _run({"floors_total": "parter"}, pipeline)
        assert result["floors_total"] is None

    def test_floors_total_none(self, pipeline: OtodomPipeline) -> None:
        """None stays None."""
        result = _run({"floors_total": None}, pipeline)
        assert result["floors_total"] is None


# ── Year built normalization ─────────────────────────────────────────────


class TestYearBuiltNormalization:
    """TC-P16: year_built normalized to int."""

    def test_year_built_string(self, pipeline: OtodomPipeline) -> None:
        """'2020' → 2020."""
        result = _run({"year_built": "2020"}, pipeline)
        assert result["year_built"] == 2020

    def test_year_built_int(self, pipeline: OtodomPipeline) -> None:
        """2020 → 2020."""
        result = _run({"year_built": 2020}, pipeline)
        assert result["year_built"] == 2020

    def test_year_built_invalid(self, pipeline: OtodomPipeline) -> None:
        """Invalid → None."""
        result = _run({"year_built": "stary"}, pipeline)
        assert result["year_built"] is None

    def test_year_built_none(self, pipeline: OtodomPipeline) -> None:
        """None stays None."""
        result = _run({"year_built": None}, pipeline)
        assert result["year_built"] is None


# ── JSONB defaults ───────────────────────────────────────────────────────


class TestJsonbDefaults:
    """TC-P17: JSONB fields default to empty dict."""

    def test_extras_default(self, pipeline: OtodomPipeline) -> None:
        """Missing extras → {}."""
        result = _run({}, pipeline)
        assert result["extras"] == {}

    def test_localization_default(self, pipeline: OtodomPipeline) -> None:
        """Missing localization → {}."""
        result = _run({}, pipeline)
        assert result["localization"] == {}

    def test_building_default(self, pipeline: OtodomPipeline) -> None:
        """Missing building → {}."""
        result = _run({}, pipeline)
        assert result["building"] == {}

    def test_extras_non_dict(self, pipeline: OtodomPipeline) -> None:
        """Non-dict extras → {}."""
        result = _run({"extras": "string_value"}, pipeline)
        assert result["extras"] == {}

    def test_extras_preserved(self, pipeline: OtodomPipeline) -> None:
        """Dict extras preserved."""
        result = _run({"extras": {"parking": True}}, pipeline)
        assert result["extras"] == {"parking": True}


# ── Default values ───────────────────────────────────────────────────────


class TestDefaults:
    """Default values for price_currency, is_active, is_canonical."""

    def test_price_currency_default(self, pipeline: OtodomPipeline) -> None:
        """Default currency is PLN."""
        result = _run({}, pipeline)
        assert result["price_currency"] == "PLN"

    def test_is_active_default(self, pipeline: OtodomPipeline) -> None:
        """Default is_active is True."""
        result = _run({}, pipeline)
        assert result["is_active"] is True

    def test_is_canonical_default(self, pipeline: OtodomPipeline) -> None:
        """Default is_canonical is True."""
        result = _run({}, pipeline)
        assert result["is_canonical"] is True


# ── Combined / integration tests ─────────────────────────────────────────


class TestCombinedNormalization:
    """Full item with all fields normalized correctly."""

    def test_full_item(self, pipeline: OtodomPipeline) -> None:
        """All fields processed in one call."""
        item: dict[str, Any] = {
            "price": "750 000 z\u0142",
            "price_per_m2": "12 500 z\u0142/m\u00b2",
            "area": "65,5 m\u00b2",
            "plot_area": "200 m2",
            "rooms": " 4 ",
            "floors_total": "5",
            "year_built": "2019",
            "photos": [
                "https://example.com/p1.jpg",
                "https://example.com/p2.jpg",
                "",
            ],
            "extras": {"balcony": True},
        }
        result = _run(item, pipeline)

        assert result["portal_source"] == "otodom"
        assert result["price"] == 750000
        assert result["price_per_m2"] == 12500
        assert result["area"] == 65.5
        assert result["plot_area"] == 200.0
        assert result["rooms"] == "4"
        assert result["floors_total"] == 5
        assert result["year_built"] == 2019
        assert result["photos"] == [
            "https://example.com/p1.jpg",
            "https://example.com/p2.jpg",
        ]
        assert result["extras"] == {"balcony": True}
        assert result["localization"] == {}
        assert result["building"] == {}
        assert result["price_currency"] == "PLN"
        assert result["is_active"] is True
        assert result["is_canonical"] is True
