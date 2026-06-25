"""
Background workers for the Real Estate Aggregation API.

Provides background task workers that consume Redis Streams and process
messages asynchronously.
"""

from app.workers.alert_worker import AlertWorker

__all__ = ["AlertWorker"]
