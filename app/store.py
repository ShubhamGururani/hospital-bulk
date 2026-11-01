from typing import Protocol

from app.models import Batch


class BatchStore(Protocol):
    def add(self, batch: Batch) -> None: ...

    def get(self, batch_id: str) -> Batch | None: ...


class InMemoryBatchStore:
    def __init__(self) -> None:
        self._batches: dict[str, Batch] = {}

    def add(self, batch: Batch) -> None:
        self._batches[batch.id] = batch

    def get(self, batch_id: str) -> Batch | None:
        return self._batches.get(batch_id)
