import asyncio
from typing import Any

import httpx

from app.models import HospitalRow


class UpstreamError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HospitalDirectoryClient:
    def __init__(self, http: httpx.AsyncClient, max_retries: int, backoff_seconds: float) -> None:
        self._http = http
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    async def create_hospital(self, row: HospitalRow, batch_id: str) -> int:
        payload: dict[str, Any] = {"name": row.name, "address": row.address, "creation_batch_id": batch_id}
        if row.phone:
            payload["phone"] = row.phone

        response = await self._request("POST", "/hospitals/", json=payload)
        try:
            return int(response.json()["id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise UpstreamError(f"Unexpected response from directory API: {response.text[:200]}") from exc

    async def activate_batch(self, batch_id: str) -> None:
        await self._request("PATCH", f"/hospitals/batch/{batch_id}/activate")

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        error = UpstreamError("Request was not attempted")
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._http.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                error = UpstreamError(f"{type(exc).__name__}: {exc}")
            else:
                if response.is_success:
                    return response
                error = UpstreamError(f"HTTP {response.status_code}: {response.text[:200]}", response.status_code)
                if not self._is_retryable(response.status_code):
                    raise error

            if attempt < self._max_retries:
                await asyncio.sleep(self._backoff_seconds * 2**attempt)

        raise error

    @staticmethod
    def _is_retryable(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500
