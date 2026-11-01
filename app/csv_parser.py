import csv
import io
from dataclasses import dataclass, field

from app.models import HospitalRow, RowError

REQUIRED_COLUMNS = ("name", "address")
FILE_LEVEL_ROW = 0


class CSVValidationError(Exception):
    def __init__(self, errors: list[RowError]) -> None:
        super().__init__("Invalid CSV")
        self.errors = errors


@dataclass
class ParseResult:
    rows: list[HospitalRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    total_rows: int = 0

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _file_error(message: str) -> ParseResult:
    return ParseResult(errors=[RowError(row=FILE_LEVEL_ROW, message=message)])


def validate_csv(content: bytes, max_rows: int) -> ParseResult:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _file_error("File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return _file_error("CSV is empty")

    reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]
    missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
    if missing:
        return _file_error(f"Missing required column(s): {', '.join(missing)}")

    result = ParseResult()
    for index, record in enumerate(reader, start=1):
        result.total_rows = index
        if any(value.strip() for value in record.pop(None, [])):
            result.errors.append(RowError(row=index, message="Row has more values than columns"))
            continue

        name = (record.get("name") or "").strip()
        address = (record.get("address") or "").strip()
        phone = (record.get("phone") or "").strip() or None

        row_errors = [
            f"'{column}' is required" for column, value in (("name", name), ("address", address)) if not value
        ]
        if row_errors:
            result.errors.extend(RowError(row=index, message=message) for message in row_errors)
            continue

        result.rows.append(HospitalRow(row=index, name=name, address=address, phone=phone))

    if result.total_rows == 0:
        result.errors.append(RowError(row=FILE_LEVEL_ROW, message="CSV contains no hospital rows"))
    elif result.total_rows > max_rows:
        result.errors.append(
            RowError(row=FILE_LEVEL_ROW, message=f"CSV has {result.total_rows} rows; maximum is {max_rows}")
        )

    return result


def parse_csv(content: bytes, max_rows: int) -> list[HospitalRow]:
    result = validate_csv(content, max_rows)
    if not result.is_valid:
        raise CSVValidationError(result.errors)
    return result.rows
