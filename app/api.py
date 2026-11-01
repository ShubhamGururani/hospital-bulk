from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)

from app.config import Settings
from app.csv_parser import parse_csv, validate_csv
from app.models import BulkResponse, ValidationResponse
from app.processor import BulkProcessor

router = APIRouter(prefix="/hospitals/bulk", tags=["bulk"])


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_processor(request: Request) -> BulkProcessor:
    processor: BulkProcessor = request.app.state.processor
    return processor


SettingsDep = Annotated[Settings, Depends(get_settings)]
ProcessorDep = Annotated[BulkProcessor, Depends(get_processor)]
CsvFile = Annotated[UploadFile, File(description="CSV with columns: name,address,phone (phone optional)")]


async def read_upload(file: UploadFile, settings: Settings) -> bytes:
    if file.filename and not file.filename.lower().endswith(".csv"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File must have a .csv extension")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is too large")
    return content


@router.post("", response_model=BulkResponse)
async def bulk_create(
    file: CsvFile,
    response: Response,
    settings: SettingsDep,
    processor: ProcessorDep,
    background: Annotated[
        bool, Query(description="Return immediately and poll GET /hospitals/bulk/{batch_id}")
    ] = False,
) -> BulkResponse:
    rows = parse_csv(await read_upload(file, settings), settings.max_csv_rows)
    if background:
        response.status_code = status.HTTP_202_ACCEPTED
        return processor.process_in_background(rows).to_response()
    return (await processor.process(rows)).to_response()


@router.post("/validate", response_model=ValidationResponse)
async def validate(file: CsvFile, settings: SettingsDep) -> ValidationResponse:
    result = validate_csv(await read_upload(file, settings), settings.max_csv_rows)
    return ValidationResponse(valid=result.is_valid, total_rows=result.total_rows, errors=result.errors)


@router.get("/{batch_id}", response_model=BulkResponse)
async def get_batch(batch_id: str, processor: ProcessorDep) -> BulkResponse:
    return processor.get(batch_id).to_response()


@router.post("/{batch_id}/resume", response_model=BulkResponse)
async def resume_batch(batch_id: str, processor: ProcessorDep) -> BulkResponse:
    return (await processor.resume(batch_id)).to_response()
