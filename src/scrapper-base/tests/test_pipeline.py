"""Tests for the BasePipeline ABC."""

import pytest

from scraper_base.pipeline import BasePipeline


class MinimalPipelineForTest(BasePipeline):  # noqa: N801
    """Concrete subclass for testing — not collected by pytest."""

    __test__ = False
    PORTAL_SOURCE = "test-portal"

    def item_to_data(self, item: dict) -> dict:
        """Convert test item to property data dict."""
        return {
            "portal_source": self.PORTAL_SOURCE,
            "source_id": item.get("source_id", "TEST-001"),
            "title": item.get("title", "Test property"),
            "price": item.get("price", 100000),
            "city": item.get("city", "Test City"),
            "property_type": item.get("property_type", "apartment"),
        }


class TestBasePipeline:
    """BasePipeline abstract class behavior."""

    def test_portal_source_required(self):
        """Subclasses must set PORTAL_SOURCE to a non-default value."""
        with pytest.raises(AttributeError, match="PORTAL_SOURCE"):

            class IncompletePipeline(BasePipeline):  # noqa: N801
                PORTAL_SOURCE = "unknown"

                def item_to_data(self, item):  # type: ignore[empty-body]
                    ...

            IncompletePipeline()

    def test_item_to_data_abstract(self):
        """item_to_data must be implemented."""
        with pytest.raises(TypeError):

            class NoItemToData(BasePipeline):  # type: ignore[misc]  # noqa: N801
                PORTAL_SOURCE = "test"

            NoItemToData()

    def test_concrete_subclass_instantiates(self):
        """A concrete subclass can be instantiated."""
        pipeline = MinimalPipelineForTest()
        assert pipeline.PORTAL_SOURCE == "test-portal"
        assert pipeline._items_scraped == 0
        assert pipeline._errors == 0

    async def test_item_to_data_converts(self):
        """item_to_data converts a raw item to a property dict."""
        pipeline = MinimalPipelineForTest()
        data = pipeline.item_to_data({"source_id": "TEST-001", "title": "Test", "price": 200000})
        assert data["portal_source"] == "test-portal"
        assert data["source_id"] == "TEST-001"
        assert data["title"] == "Test"
        assert data["price"] == 200000

    async def test_process_item_calls_item_to_data(self, db_session, monkeypatch):
        """process_item calls item_to_data and persists."""
        from scraper_base.services import PropertyService  # noqa: PLC0415

        pipeline = MinimalPipelineForTest()
        pipeline._session = db_session
        pipeline._property_service = PropertyService(db_session)

        item = {"source_id": "PIPE-001", "title": "Pipeline test", "city": "Gdańsk", "price": 300000}  # noqa: E501
        result = await pipeline.process_item(item, None)  # type: ignore[arg-type]

        assert pipeline._items_scraped == 1
        assert pipeline._items_new == 1
        assert result is not None
        assert result.get("source_id") == "PIPE-001"

    async def test_pipeline_error_increments_errors(self, db_session):
        """Errors in process_item increment the error counter."""
        pipeline = MinimalPipelineForTest()
        pipeline._session = db_session
        pipeline._session.rollback = lambda: None  # type: ignore[method-assign]

        from unittest.mock import MagicMock  # noqa: PLC0415

        from scraper_base.services import PropertyService  # noqa: PLC0415

        pipeline._property_service = MagicMock(spec=PropertyService)
        pipeline._property_service.upsert_property = MagicMock(side_effect=ValueError("Test error"))

        with pytest.raises(ValueError):
            await pipeline.process_item({"source_id": "ERR-001"}, None)  # type: ignore[arg-type]

        assert pipeline._errors == 1
