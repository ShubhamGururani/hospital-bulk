import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    directory_api_url: str = "https://hospital-directory.onrender.com"
    max_csv_rows: int = 20
    max_upload_bytes: int = 1_000_000
    max_concurrency: int = 5
    request_timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_backoff_seconds: float = 0.5

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            directory_api_url=os.getenv("DIRECTORY_API_URL", defaults.directory_api_url),
            max_csv_rows=int(os.getenv("MAX_CSV_ROWS", defaults.max_csv_rows)),
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", defaults.max_upload_bytes)),
            max_concurrency=int(os.getenv("MAX_CONCURRENCY", defaults.max_concurrency)),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", defaults.request_timeout_seconds)),
            max_retries=int(os.getenv("MAX_RETRIES", defaults.max_retries)),
            retry_backoff_seconds=float(os.getenv("RETRY_BACKOFF_SECONDS", defaults.retry_backoff_seconds)),
        )
