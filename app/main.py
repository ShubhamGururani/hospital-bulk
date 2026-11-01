import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api import router
from app.client import HospitalDirectoryClient
from app.config import Settings
from app.csv_parser import CSVValidationError
from app.processor import BatchInProgressError, BatchNotFoundError, BulkProcessor
from app.store import InMemoryBatchStore


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(
            base_url=settings.directory_api_url,
            timeout=settings.request_timeout_seconds,
            transport=transport,
        ) as http:
            client = HospitalDirectoryClient(http, settings.max_retries, settings.retry_backoff_seconds)
            processor = BulkProcessor(client, InMemoryBatchStore(), settings.max_concurrency)
            app.state.settings = settings
            app.state.processor = processor
            yield
            await processor.shutdown()

    app = FastAPI(
        title="Hospital Bulk Processing API",
        version="1.0.0",
        description="Bulk-creates hospitals from a CSV via the Hospital Directory API.",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.exception_handler(CSVValidationError)
    async def csv_error_handler(_: Request, exc: CSVValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid CSV", "errors": [error.model_dump() for error in exc.errors]},
        )

    @app.exception_handler(BatchNotFoundError)
    async def not_found_handler(_: Request, exc: BatchNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": f"Batch {exc} not found"})

    @app.exception_handler(BatchInProgressError)
    async def in_progress_handler(_: Request, exc: BatchInProgressError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content={"detail": f"Batch {exc} is still processing"}
        )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


logging.basicConfig(level=logging.INFO)
app = create_app()
