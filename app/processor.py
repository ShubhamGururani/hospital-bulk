import asyncio
import logging
import time
from collections.abc import Coroutine
from typing import Any

from app.client import HospitalDirectoryClient, UpstreamError
from app.models import Batch, BatchStatus, HospitalRow, HospitalStatus
from app.store import BatchStore

logger = logging.getLogger(__name__)


class BatchNotFoundError(Exception):
    pass


class BatchInProgressError(Exception):
    pass


class BulkProcessor:
    def __init__(self, client: HospitalDirectoryClient, store: BatchStore, max_concurrency: int) -> None:
        self._client = client
        self._store = store
        self._max_concurrency = max_concurrency
        self._background_tasks: set[asyncio.Task[None]] = set()

    def get(self, batch_id: str) -> Batch:
        batch = self._store.get(batch_id)
        if batch is None:
            raise BatchNotFoundError(batch_id)
        return batch

    async def process(self, rows: list[HospitalRow]) -> Batch:
        batch = self._register(rows)
        await self._run(batch)
        return batch

    def process_in_background(self, rows: list[HospitalRow]) -> Batch:
        batch = self._register(rows)
        self._spawn(self._run_safely(batch))
        return batch

    async def resume(self, batch_id: str) -> Batch:
        batch = self.get(batch_id)
        if batch.status is BatchStatus.PROCESSING:
            raise BatchInProgressError(batch_id)
        if batch.activated:
            return batch

        batch.status = BatchStatus.PROCESSING
        batch.error = None
        await self._run(batch)
        return batch

    async def shutdown(self) -> None:
        for task in self._background_tasks:
            task.cancel()
        await asyncio.gather(*self._background_tasks, return_exceptions=True)

    def _register(self, rows: list[HospitalRow]) -> Batch:
        batch = Batch.new(rows)
        self._store.add(batch)
        return batch

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _run_safely(self, batch: Batch) -> None:
        try:
            await self._run(batch)
        except Exception as exc:
            logger.exception("Batch %s crashed", batch.id)
            batch.status = BatchStatus.FAILED
            batch.error = f"Unexpected error: {exc}"

    async def _run(self, batch: Batch) -> None:
        started = time.perf_counter()
        semaphore = asyncio.Semaphore(self._max_concurrency)
        try:
            await asyncio.gather(*(self._create(batch, row, semaphore) for row in batch.rows_to_process()))
            await self._activate_if_complete(batch)
        finally:
            batch.processing_time_seconds += time.perf_counter() - started

    async def _create(self, batch: Batch, row: HospitalRow, semaphore: asyncio.Semaphore) -> None:
        result = batch.results[row.row]
        async with semaphore:
            try:
                result.hospital_id = await self._client.create_hospital(row, batch.id)
            except UpstreamError as exc:
                result.status = HospitalStatus.FAILED
                result.error = str(exc)
                return
        result.status = HospitalStatus.CREATED
        result.error = None

    async def _activate_if_complete(self, batch: Batch) -> None:
        failed = batch.count(HospitalStatus.FAILED)
        if failed:
            batch.status = BatchStatus.FAILED
            batch.error = f"{failed} hospital(s) failed to create; batch not activated. Retry via resume."
            return

        try:
            await self._client.activate_batch(batch.id)
        except UpstreamError as exc:
            batch.status = BatchStatus.FAILED
            batch.error = f"Batch activation failed: {exc}. Retry via resume."
            return

        for result in batch.results.values():
            result.status = HospitalStatus.CREATED_AND_ACTIVATED
        batch.activated = True
        batch.status = BatchStatus.COMPLETED
        batch.error = None
