from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel


class HospitalStatus(str, Enum):
    PENDING = "pending"
    CREATED = "created"
    CREATED_AND_ACTIVATED = "created_and_activated"
    FAILED = "failed"


class BatchStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class HospitalRow(BaseModel):
    row: int
    name: str
    address: str
    phone: str | None = None


class HospitalResult(BaseModel):
    row: int
    hospital_id: int | None = None
    name: str
    status: HospitalStatus = HospitalStatus.PENDING
    error: str | None = None


class BulkResponse(BaseModel):
    batch_id: str
    status: BatchStatus
    total_hospitals: int
    processed_hospitals: int
    failed_hospitals: int
    processing_time_seconds: float
    processing_time_inner: float
    batch_activated: bool
    error: str | None = None
    hospitals: list[HospitalResult]


class RowError(BaseModel):
    row: int
    message: str


class ValidationResponse(BaseModel):
    valid: bool
    total_rows: int
    errors: list[RowError]


@dataclass
class Batch:
    id: str
    rows: list[HospitalRow]
    results: dict[int, HospitalResult]
    status: BatchStatus = BatchStatus.PROCESSING
    activated: bool = False
    error: str | None = None
    processing_time_seconds: float = 0.0
    processing_time_inner: float = 0.0

    @classmethod
    def new(cls, rows: list[HospitalRow]) -> Batch:
        return cls(
            id=str(uuid.uuid4()),
            rows=rows,
            results={row.row: HospitalResult(row=row.row, name=row.name) for row in rows},
        )

    def rows_to_process(self) -> list[HospitalRow]:
        retryable = {HospitalStatus.PENDING, HospitalStatus.FAILED}
        return [row for row in self.rows if self.results[row.row].status in retryable]

    def count(self, *statuses: HospitalStatus) -> int:
        return sum(1 for result in self.results.values() if result.status in statuses)

    def to_response(self) -> BulkResponse:
        return BulkResponse(
            batch_id=self.id,
            status=self.status,
            total_hospitals=len(self.rows),
            processed_hospitals=self.count(HospitalStatus.CREATED, HospitalStatus.CREATED_AND_ACTIVATED),
            failed_hospitals=self.count(HospitalStatus.FAILED),
            processing_time_seconds=round(self.processing_time_seconds, 3),
            processing_time_inner = round(self.processing_time_inner, 3),
            batch_activated=self.activated,
            error=self.error,
            hospitals=[result.model_copy() for result in self.results.values()],
        )
